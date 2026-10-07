"""Versioned, non-executable station archives.

The caller owns admission/draining and the database snapshot/transaction. Staging
and destination parents must be private service directories (including their
Windows ACLs), never the public capture root. No uploaded SQL is executed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path, PurePosixPath
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, Float, Integer, JSON, Numeric
from sqlalchemy import String, UniqueConstraint, Uuid, insert, select
from sqlalchemy.dialects.postgresql import ARRAY

from app import models  # noqa: F401 -- register application-owned metadata
from app.core.database import Base
from app.core.db_types import ManilaDateTime
from app.core.time import now_manila

TABLE_NAMES = frozenset({
    "user_role", "user_account", "admin_profile", "operator_profile", "supplier",
    "delivery_intake", "scan", "scan_classification", "scan_status_log",
    "scan_original_ai_result", "scan_detection", "scan_image", "scan_note", "device",
    "activity_log", "system_config", "app_notification", "sensor_reading",
})
MAX_ARCHIVE_BYTES = 4 * 1024**3
MAX_EXPANDED_BYTES = 8 * 1024**3
MAX_FILE_BYTES = 256 * 1024**2
MAX_MANIFEST_BYTES = 16 * 1024**2
MAX_ROW_BYTES = 1024**2
MAX_ROWS = 1_000_000
MAX_MEMBERS = 50_000
MAX_EXPANSION_RATIO = 1000
CHUNK = 64 * 1024
RESERVE_BYTES = 16 * 1024**2
EVIDENCE_COLUMNS = {("scan_image", "file_path"), ("scan_classification", "thumbnail_url")}


class ArchiveError(ValueError):
    """Archive is incomplete, incompatible, unsafe, or could not be written."""


def application_tables():
    """Trusted dependency ordering, explicitly excluding maintenance control data."""
    return [table for table in Base.metadata.sorted_tables if table.name in TABLE_NAMES]


def _type_spec(kind):
    if isinstance(kind, SAEnum):
        return {"kind": "enum", "values": [e.value for e in kind.enum_class]}
    if isinstance(kind, (ManilaDateTime, DateTime)):
        return {"kind": "timestamp"}
    if isinstance(kind, ARRAY):
        return {"kind": "array", "item": _type_spec(kind.item_type), "dimensions": kind.dimensions}
    if isinstance(kind, Boolean):
        return {"kind": "boolean"}
    if isinstance(kind, Integer):
        return {"kind": "integer"}
    if isinstance(kind, Float):
        return {"kind": "float"}
    if isinstance(kind, Numeric):
        return {"kind": "decimal", "precision": kind.precision, "scale": kind.scale}
    if isinstance(kind, Uuid):
        return {"kind": "uuid"}
    if isinstance(kind, Date):
        return {"kind": "date"}
    if isinstance(kind, JSON):
        return {"kind": "json"}
    if isinstance(kind, String):
        return {"kind": "string", "length": kind.length}
    raise ArchiveError("Unsupported application column type")


def schema_description():
    return {t.name: {c.name: dict(_type_spec(c.type), nullable=c.nullable,
                   primary_key=c.primary_key,
                   foreign_keys=sorted(f.target_fullname for f in c.foreign_keys))
                    for c in t.columns} for t in application_tables()}


def _dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArchiveError("Duplicate JSON key")
        result[key] = value
    return result


def _load(data):
    try:
        return json.loads(data, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ArchiveError("Nonfinite JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ArchiveError("Invalid archive JSON") from exc


def _encode(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


def _typed(value, kind):
    """Strict wire types; never coerce bool to integer or strings to JSON."""
    spec = _type_spec(kind)
    label = spec["kind"]
    try:
        if label == "enum":
            if not isinstance(value, str):
                raise ValueError()
            return kind.enum_class(value)
        if label == "timestamp":
            if not isinstance(value, str):
                raise ValueError()
            result = datetime.fromisoformat(value)
            if result.tzinfo is None or result.utcoffset() is None:
                raise ValueError()
            return result
        if label == "date":
            return date.fromisoformat(value)
        if label == "uuid":
            result = UUID(value)
            if str(result) != value:
                raise ValueError()
            return result
        if label == "boolean" and type(value) is bool:
            return value
        if label == "integer" and type(value) is int and -(2**31) <= value < 2**31:
            return value
        if label == "float" and type(value) in (float, int) and math.isfinite(value):
            return float(value)
        if label == "decimal" and isinstance(value, str):
            result = Decimal(value)
            if not result.is_finite():
                raise ValueError()
            precision, scale = kind.precision, kind.scale
            if scale is not None and result != result.quantize(Decimal(1).scaleb(-scale)):
                raise ValueError()
            if precision is not None and scale is not None and abs(result) >= Decimal(10) ** (precision - scale):
                raise ValueError()
            return result
        if label == "string" and isinstance(value, str) and "\x00" not in value:
            if kind.length is None or len(value) <= kind.length:
                return value
        if label == "json":
            _dump(value)
            return value
        if label == "array" and isinstance(value, list):
            def elements(items, dimensions):
                if not isinstance(items, list):
                    raise ValueError()
                if dimensions > 1:
                    return [elements(item, dimensions - 1) for item in items]
                return [None if item is None else _typed(item, kind.item_type) for item in items]
            return elements(value, kind.dimensions or 1)
    except (ValueError, TypeError, AttributeError, InvalidOperation, OverflowError) as exc:
        raise ArchiveError(f"Invalid {label} value") from exc
    raise ArchiveError(f"Invalid {label} value")


def _row(table, value):
    if not isinstance(value, dict) or set(value) != set(table.columns.keys()):
        raise ArchiveError("Unexpected table columns")
    result = {}
    for column in table.columns:
        item = value[column.name]
        if item is None:
            if not column.nullable:
                raise ArchiveError("Null in required column")
            result[column.name] = None
        else:
            result[column.name] = _typed(item, column.type)
    return result


def _safe_name(name):
    if not isinstance(name, str) or len(name) > 500 or not name or "\\" in name:
        raise ArchiveError("Unsafe archive path")
    parts = name.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    for part in parts:
        if (part in ("", ".", "..") or part.endswith((".", " "))
                or not re.fullmatch(r"[A-Za-z0-9_.-]+", part)
                or part.split(".")[0].upper() in reserved):
            raise ArchiveError("Unsafe archive path")
    return name


def _no_links(path):
    """Check all existing ancestors; junctions and symlinks are both forbidden."""
    for current in (path, *path.parents):
        try:
            entry = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(entry.st_mode) or getattr(entry, "st_file_attributes", 0) & 0x400:
            raise ArchiveError("Symlink or reparse point is not allowed")


def _evidence_name(value, capture_root=None):
    if value.startswith("/captures/"):
        return _safe_name(value[len("/captures/"):])
    if capture_root is None:
        raise ArchiveError("Evidence reference must be normalized")
    text = value.replace("\\", "/")
    root = capture_root.absolute()
    candidate = Path(value)
    if candidate.is_absolute():
        _no_links(candidate)
        try:
            return _safe_name(candidate.absolute().relative_to(root).as_posix())
        except ValueError as exc:
            raise ArchiveError("Evidence outside capture root") from exc
    if text.startswith(root.name + "/"):
        text = text[len(root.name) + 1:]
    return _safe_name(text)


def _space(path, required):
    if shutil.disk_usage(path).free < required + RESERVE_BYTES:
        raise ArchiveError("Insufficient disk space")


def _private_dir(parent, prefix):
    parent = parent.absolute()
    _no_links(parent)
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _no_links(parent)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=parent))


def _hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ValidatedBackup:
    manifest: dict
    staging_root: Path
    evidence_root: Path
    evidence: dict[str, Path]
    archive_sha256: str

    def iter_rows(self, table_name):
        if table_name not in TABLE_NAMES:
            raise ArchiveError("Unknown table")
        table = Base.metadata.tables[table_name]
        path = self.staging_root / "tables" / f"{table_name}.jsonl"
        _no_links(path)
        if _hash_file(path) != self.manifest["tables"][table_name]["sha256"]:
            raise ArchiveError("Staged table changed")
        with path.open("rb") as source:
            for line in source:
                if len(line) > MAX_ROW_BYTES:
                    raise ArchiveError("Row size limit exceeded")
                yield _row(table, _load(line))


def _descriptor(size, digest, count=None):
    result = {"size": size, "sha256": digest}
    if count is not None:
        result["count"] = count
    return result


def model_prerequisites():
    from app.config import get_settings
    settings = get_settings()
    result = {}
    for name, configured in [('classifier', settings.yolo_model_path), ('spoilage', settings.rfr_model_path)]:
        path = Path(configured)
        result[name] = {'filename': path.name, 'sha256': _hash_file(path) if path.is_file() else None}
    return result


async def create_archive(db, capture_root: Path, destination: Path) -> dict:
    """Stream a drained, consistent database snapshot and all referenced evidence."""
    capture_root, destination = Path(capture_root).absolute(), Path(destination).absolute()
    _no_links(capture_root)
    _no_links(destination)
    if destination.is_relative_to(capture_root):
        raise ArchiveError("Backup destination must be private")
    owned = _private_dir(destination.parent, ".backup-")
    partial = owned / "archive.zip"
    try:
        _space(owned, RESERVE_BYTES)
        manifest = {"format": "bananavision-station", "version": 1,
                    "application_version": "0.1.0", "created_at": now_manila().isoformat(),
                    "schema": schema_description(), "tables": {}, "files": {},
                    "prerequisites": {"database": "PostgreSQL", "timezone": "Asia/Manila",
                                      "models": model_prerequisites()}}
        references = {}
        total = 0
        total_rows = 0
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            os.chmod(partial, 0o600)
            for table in application_tables():
                digest, size, count = hashlib.sha256(), 0, 0
                with archive.open(f"tables/{table.name}.jsonl", "w", force_zip64=True) as output:
                    while True:
                        query = select(table).order_by(*table.primary_key.columns).limit(100).offset(count)
                        records = (await db.execute(query)).mappings().all()
                        if not records:
                            break
                        for record in records:
                            row = {key: _encode(value) for key, value in record.items()}
                            for owner, column in EVIDENCE_COLUMNS:
                                if owner == table.name and row[column] is not None:
                                    relative = _evidence_name(row[column], capture_root)
                                    row[column] = f"/captures/{relative}"
                                    references[relative] = capture_root / PurePosixPath(relative)
                                    if len(references) + len(TABLE_NAMES) + 1 > MAX_MEMBERS:
                                        raise ArchiveError("File count limit exceeded")
                            _row(table, row)
                            line = _dump(row) + b"\n"
                            if len(line) > MAX_ROW_BYTES:
                                raise ArchiveError("Row size limit exceeded")
                            total += len(line)
                            size += len(line)
                            count += 1
                            total_rows += 1
                            if total > MAX_EXPANDED_BYTES or total_rows > MAX_ROWS:
                                raise ArchiveError("Archive size/row limit exceeded")
                            output.write(line)
                            digest.update(line)
                manifest["tables"][table.name] = _descriptor(size, digest.hexdigest(), count)
            for relative, source in sorted(references.items()):
                _no_links(source)
                if not source.is_file():
                    raise ArchiveError("Missing referenced evidence")
                length = source.stat().st_size
                if length > MAX_FILE_BYTES or total + length > MAX_EXPANDED_BYTES:
                    raise ArchiveError("Evidence size limit exceeded")
                _space(owned, length)
                digest, length_read = hashlib.sha256(), 0
                with source.open("rb") as evidence, archive.open(f"evidence/{relative}", "w", force_zip64=True) as output:
                    for chunk in iter(lambda: evidence.read(CHUNK), b""):
                        length_read += len(chunk)
                        if length_read > length:
                            raise ArchiveError("Evidence changed during backup")
                        output.write(chunk)
                        digest.update(chunk)
                if length_read != length:
                    raise ArchiveError("Evidence changed during backup")
                total += length
                manifest["files"][relative] = _descriptor(length, digest.hexdigest())
            encoded = _dump(manifest)
            if len(encoded) > MAX_MANIFEST_BYTES:
                raise ArchiveError("Manifest size limit exceeded")
            archive.writestr("manifest.json", encoded)
        with partial.open("r+b") as stream:
            os.fsync(stream.fileno())
        validated = validate_archive(partial, owned / "verification")
        shutil.rmtree(validated.staging_root)
        os.replace(partial, destination)
        return manifest
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, ArchiveError):
            raise
        raise ArchiveError("Could not create complete backup") from exc
    finally:
        shutil.rmtree(owned)


def _validate_descriptor(value, *, rows=False):
    expected = {"size", "sha256", "count"} if rows else {"size", "sha256"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ArchiveError("Invalid file descriptor")
    if type(value["size"]) is not int or not 0 <= value["size"] <= MAX_EXPANDED_BYTES:
        raise ArchiveError("File size limit exceeded")
    if not isinstance(value["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", value["sha256"]):
        raise ArchiveError("Invalid file digest")
    if rows and (type(value["count"]) is not int or not 0 <= value["count"] <= MAX_ROWS):
        raise ArchiveError("Row count limit exceeded")


def _copy_member(archive, name, destination, descriptor):
    digest, length = hashlib.sha256(), 0
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with archive.open(name) as source, destination.open("xb") as output:
        os.chmod(destination, 0o600)
        for chunk in iter(lambda: source.read(CHUNK), b""):
            length += len(chunk)
            if length > descriptor["size"]:
                raise ArchiveError("Expanded file size limit exceeded")
            digest.update(chunk)
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    if length != descriptor["size"] or digest.hexdigest() != descriptor["sha256"]:
        raise ArchiveError("File size/hash mismatch")


def _check_constraints(validated):
    """Disk-backed key validation keeps memory independent of table row counts.

    SQL identifiers below come exclusively from application metadata. PostgreSQL
    staging remains mandatory for database-specific checks and partial indexes.
    """
    connection = sqlite3.connect(validated.staging_root / "constraints.sqlite")
    try:
        connection.execute("PRAGMA cache_size=-2048")
        connection.execute("PRAGMA temp_store=FILE")
        references = set()
        for table in application_tables():
            names = list(table.columns.keys())
            cols = ",".join(f'"{name}" TEXT' for name in names)
            connection.execute(f'CREATE TABLE "{table.name}" ({cols})')
            unique = {tuple(c.name for c in table.primary_key.columns)}
            unique.update(tuple(c.name for c in constraint.columns)
                          for constraint in table.constraints if isinstance(constraint, UniqueConstraint))
            unique.update(tuple(c.name for c in idx.columns) for idx in table.indexes if idx.unique
                          and idx.dialect_options["postgresql"].get("where") is None)
            for number, fields in enumerate(sorted(unique)):
                columns = ",".join(f'"{field}"' for field in fields)
                connection.execute(f'CREATE UNIQUE INDEX "u_{table.name}_{number}" ON "{table.name}" ({columns})')
            count = 0
            with (validated.staging_root / "tables" / f"{table.name}.jsonl").open("rb") as source:
                while line := source.readline(MAX_ROW_BYTES + 1):
                    if len(line) > MAX_ROW_BYTES or not line.endswith(b"\n"):
                        raise ArchiveError("Row size/framing limit exceeded")
                    row = _row(table, _load(line))
                    for owner, column in EVIDENCE_COLUMNS:
                        if owner == table.name and row[column] is not None:
                            references.add(_evidence_name(row[column]))
                            if len(references) > MAX_MEMBERS:
                                raise ArchiveError("Evidence count limit exceeded")
                    values = [None if row[name] is None else _dump(_encode(row[name])).decode() for name in names]
                    placeholders = ",".join("?" for _ in names)
                    connection.execute(f'INSERT INTO "{table.name}" VALUES ({placeholders})', values)
                    count += 1
                    if count > validated.manifest["tables"][table.name]["count"]:
                        raise ArchiveError("Table count mismatch")
            if count != validated.manifest["tables"][table.name]["count"]:
                raise ArchiveError("Table count mismatch")
        if references != set(validated.evidence):
            raise ArchiveError("Missing or unreferenced evidence")
        for table in application_tables():
            for fk in table.foreign_key_constraints:
                target = fk.referred_table.name
                joins = " AND ".join(f'a."{f.parent.name}"=b."{f.column.name}"' for f in fk.elements)
                nonnull = " AND ".join(f'a."{f.parent.name}" IS NOT NULL' for f in fk.elements)
                first = list(fk.elements)[0].column.name
                if connection.execute(f'SELECT 1 FROM "{table.name}" a LEFT JOIN "{target}" b ON {joins} WHERE {nonnull} AND b."{first}" IS NULL LIMIT 1').fetchone():
                    raise ArchiveError("Broken foreign key")
        admins = connection.execute('''SELECT a.password_hash FROM user_account a
            JOIN user_role r ON a.role_id=r.id JOIN admin_profile p ON p.account_id=a.id
            WHERE r.name=? AND a.status=? AND a.requires_password_change='false' ''', ('"Admin"', '"Active"'))
        # Accepted hash shape is bcrypt, the application's actual password verifier.
        if not any(re.fullmatch(r"\$2[aby]\$(?:0[4-9]|1[0-6])\$[./A-Za-z0-9]{53}", json.loads(row[0])) for row in admins):
            raise ArchiveError("Backup has no usable active administrator")
    except sqlite3.IntegrityError as exc:
        raise ArchiveError("Duplicate primary or unique key") from exc
    finally:
        connection.close()
        (validated.staging_root / "constraints.sqlite").unlink(missing_ok=True)


def validate_archive(archive: Path, staging_root: Path) -> ValidatedBackup:
    """Validate every byte and typed row into a new private staging directory."""
    archive, staging_root = Path(archive).absolute(), Path(staging_root).absolute()
    owned = None
    try:
        _no_links(archive)
        if archive.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ArchiveError("Archive size limit exceeded")
        with zipfile.ZipFile(archive) as source:
            members = source.infolist()
            if len(members) > MAX_MEMBERS:
                raise ArchiveError("Member count limit exceeded")
            names = set()
            expanded = 0
            for member in members:
                name = _safe_name(member.filename)
                if name.casefold() in names:
                    raise ArchiveError("Duplicate archive path")
                names.add(name.casefold())
                mode = member.external_attr >> 16
                if stat.S_IFMT(mode) not in (0, stat.S_IFREG) or member.external_attr & 0x410:
                    raise ArchiveError("Archive link/reparse/directory entry")
                if member.flag_bits & 1 or member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise ArchiveError("Unsupported ZIP encoding")
                expanded += member.file_size
                if expanded > MAX_EXPANDED_BYTES or member.file_size > max(member.compress_size, 1) * MAX_EXPANSION_RATIO:
                    raise ArchiveError("Archive expansion limit exceeded")
            if "manifest.json" not in names or source.getinfo("manifest.json").file_size > MAX_MANIFEST_BYTES:
                raise ArchiveError("Missing or oversized manifest")
            manifest = _load(source.read("manifest.json"))
            expected = {"format", "version", "application_version", "created_at", "schema", "tables", "files", "prerequisites"}
            if not isinstance(manifest, dict) or set(manifest) != expected:
                raise ArchiveError("Unexpected manifest fields")
            if manifest["format"] != "bananavision-station" or type(manifest["version"]) is not int or manifest["version"] != 1:
                raise ArchiveError("Unsupported archive version")
            if manifest["application_version"] != "0.1.0" or manifest["schema"] != schema_description():
                raise ArchiveError("Incompatible archive schema")
            _typed(manifest["created_at"], ManilaDateTime())
            if not isinstance(manifest["tables"], dict) or set(manifest["tables"]) != TABLE_NAMES:
                raise ArchiveError("Unexpected application tables")
            if not isinstance(manifest["files"], dict):
                raise ArchiveError("Invalid evidence manifest")
            expected_members = {"manifest.json"}
            row_count = 0
            for name, descriptor in manifest["tables"].items():
                _validate_descriptor(descriptor, rows=True)
                row_count += descriptor["count"]
                expected_members.add(f"tables/{name}.jsonl")
            if row_count > MAX_ROWS:
                raise ArchiveError("Total row limit exceeded")
            for name, descriptor in manifest["files"].items():
                _safe_name(name)
                _validate_descriptor(descriptor)
                if descriptor["size"] > MAX_FILE_BYTES:
                    raise ArchiveError("Evidence size limit exceeded")
                expected_members.add(f"evidence/{name}")
            if expected_members != {member.filename for member in members}:
                raise ArchiveError("Unexpected or missing archive member")
            owned = _private_dir(staging_root, "validated-")
            _space(owned, expanded * 3)
            evidence_root = owned / "evidence"
            evidence_root.mkdir(mode=0o700)
            evidence = {}
            for name, descriptor in manifest["tables"].items():
                member = f"tables/{name}.jsonl"
                _copy_member(source, member, owned / "tables" / f"{name}.jsonl", descriptor)
            for name, descriptor in manifest["files"].items():
                # Only normalized manifest references are used, never extract/extractall.
                path = evidence_root.joinpath(*name.split("/"))
                _copy_member(source, f"evidence/{name}", path, descriptor)
                evidence[name] = path
        validated = ValidatedBackup(manifest, owned, evidence_root, evidence, _hash_file(archive))
        _check_constraints(validated)
        return validated
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile,
            sqlite3.Error, EOFError, RecursionError) as exc:
        if owned is not None:
            shutil.rmtree(owned)
        if isinstance(exc, ArchiveError):
            raise
        raise ArchiveError("Invalid or unreadable backup archive") from exc


async def restore_rows(db, validated: ValidatedBackup):
    """Insert trusted typed values into empty application tables; caller commits."""
    for table in application_tables():
        batch = []
        for row in validated.iter_rows(table.name):
            batch.append(row)
            if len(batch) == 100:
                await db.execute(insert(table).values(batch))
                batch = []
        if batch:
            await db.execute(insert(table).values(batch))
