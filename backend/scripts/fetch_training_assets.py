"""Fetch the training dataset and weights onto this machine, without a laptop.

Never reads the station database, captures or cameras, and never loads a model.
Run from backend/. --dest must be a new or empty directory; nothing outside it is
written.

github  Download the assets of one GitHub release into --dest. Uses the gh CLI
        (`gh release download`) when it is installed, otherwise the GitHub REST API:
        GET /repos/{owner}/{repo}/releases/tags/{tag}, then each asset through its API
        URL with Accept: application/octet-stream (--method picks one explicitly).
        When gh is installed but not logged in and no token is set, --method auto
        uses the REST API, which reads a public release without a token.
        --asset PATTERN (glob, repeatable) limits the assets; a SHA256SUMS asset (any
        letter case) is always fetched with them. A token, if any, is read from the
        environment variable named by --token-env (default GITHUB_TOKEN; gh also uses
        its own login) and must be one word of printable ASCII. It is sent only in the
        Authorization header to api.github.com (never forwarded on a redirect; gh
        receives it as GH_TOKEN in its environment) and is never printed, logged,
        written to a file or put in a URL or an error.
local   The same verification, extraction and report for a file already on disk, for
        example a file attached to the chat. --sha256 HEX and/or --checksums
        SHA256SUMS verify it first; the archive itself is never modified.

Verification fails closed: when a SHA256SUMS asset is present (or --require-checksums
is given), every other downloaded file must be listed in it with a matching SHA-256.
On a mismatch, a missing entry or a missing SHA256SUMS the downloads are removed and
nothing is extracted. Without SHA256SUMS the report gives every file's SHA-256 to
compare with the publisher.

.zip, .tar, .tar.gz/.tgz, .tar.bz2 and .tar.xz files are extracted into
<dest>/<archive stem>/. Every member is checked before anything is written: absolute
paths, '..' components, backslashes, symbolic and hard links, device/FIFO/special
files, encrypted or duplicate members, more than the total-size limit and
compression ratios that look like a zip bomb are refused. Files are created with
default permissions; archive modes and owners are not applied.

The report (JSON on stdout) lists the files with their SHA-256, the YOLO exports found
(data.yaml with train/valid/test images/labels, Roboflow style), the *.pt weights with
their SHA-256, and the next commands: prepare_yolo_dataset.py, then
evaluate_finger_count.py and train_finger_model.py. Its warnings name what those
scripts would refuse: a data.yaml that prepare_yolo_dataset.py cannot read (it needs
an inline names: [...] line and nc: 12), the 12 classes in another order than
EXPECTED_NAMES, a prepared copy whose data.yaml path: names another machine's folder,
and several *.pt files (the commands then use the only best.pt, or a placeholder).
Weights are pickles: only use a release you trust; this script hashes them but never
loads them.

Roboflow downloads are not implemented: the Roboflow API takes the key as a URL query
parameter. Ask the teammate to attach the Roboflow export zip (YOLO format) to the
GitHub release instead, ideally with a SHA256SUMS file (`sha256sum * > SHA256SUMS`).

Examples (keep datasets and weights out of commits):
  python scripts/fetch_training_assets.py github --repo <owner>/<repo> --tag <tag> \\
      --dest ../training-assets
  python scripts/fetch_training_assets.py github --repo <owner>/<repo> --tag <tag> \\
      --asset '*.zip' --asset '*.pt' --dest ../training-assets --method api
  python scripts/fetch_training_assets.py local --archive <export>.zip \\
      --sha256 <published SHA-256> --dest ../training-assets
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import hashlib
import http.client
import json
import lzma
import os
import re
import shlex
import shutil
import ssl
import stat
import subprocess
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.time import now_manila  # noqa: E402
from scripts.prepare_yolo_dataset import (  # noqa: E402
    EXPECTED_NAMES,
    IMAGE_SUFFIXES,
    SPLITS,
    PreparationError,
)
from scripts.prepare_yolo_dataset import _names as prepare_names  # noqa: E402

API_ROOT = "https://api.github.com"
USER_AGENT = "bananavision-fetch-training-assets"
TIMEOUT_SECONDS = 60
CHUNK = 1 << 20
MAX_METADATA_BYTES = 16 << 20
MAX_CHECKSUM_BYTES = 1 << 20
MAX_YAML_BYTES = 1 << 20
# Extraction limits: a dataset export is a few GB of photos and small label files.
MAX_TOTAL_BYTES = 64 << 30
MAX_RATIO = 100
MAX_MEMBERS = 500_000
RATIO_FLOOR = 1 << 20  # ratios of tiny archives and members say nothing
CHECKSUM_NAMES = ("SHA256SUMS", "SHA256SUMS.txt", "sha256sums.txt")
ARCHIVE_SUFFIXES = (
    (".tar.gz", "tar"), (".tgz", "tar"), (".tar.bz2", "tar"), (".tar.xz", "tar"),
    (".tar", "tar"), (".zip", "zip"),
)
# Corrupt or unsupported compressed data; gzip/bz2 stream errors are OSError already.
ARCHIVE_ERRORS = (
    zipfile.BadZipFile, tarfile.TarError, EOFError, zlib.error, lzma.LZMAError,
    NotImplementedError,
)
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}")
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}")
TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+-]{0,254}")
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
# A token is one printable ASCII word: anything else could end up echoed in an error.
TOKEN_VALUE = re.compile(r"[\x21-\x7e]+")
ASSET_URL = re.compile(
    r"https://api\.github\.com/repos/([A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100})"
    r"/releases/assets/[0-9]+"
)
RELEASE_URL = re.compile(
    r"https://api\.github\.com/repos/([A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100})"
    r"/releases/[0-9]+"
)
SKIPPED_TOP_DIRS = {"__MACOSX"}
WEIGHTS_PLACEHOLDER = "<file named by YOLO_MODEL_PATH>"
GH_AUTH_REQUIRED = 4  # gh's exit code when it has no login and no GH_TOKEN

Runner = Callable[[list[str], dict[str, str]], subprocess.CompletedProcess]


class FetchError(ValueError):
    """Unsafe input, a failed download or verification, or an unsafe archive."""


class GhAuthRequiredError(FetchError):
    """gh has no login; --method auto falls back to the REST API."""


@dataclass(frozen=True)
class Limits:
    max_total_bytes: int = MAX_TOTAL_BYTES
    max_ratio: float = MAX_RATIO
    max_members: int = MAX_MEMBERS


@dataclass
class Member:
    parts: tuple[str, ...]
    is_dir: bool
    size: int
    source: object  # zipfile.ZipInfo or tarfile.TarInfo


# ── Inputs and the destination ─────────────────────────────────────────────────


def redact(text: str, secret: str | None) -> str:
    """Last line of defence: no message leaves main() with the token in it."""
    return text.replace(secret, "***") if secret else text


def read_token(env_name: str) -> str | None:
    if not ENV_NAME.fullmatch(env_name):
        raise FetchError("--token-env must name an environment variable")
    value = os.environ.get(env_name, "").strip()
    if value and not TOKEN_VALUE.fullmatch(value):
        # The value is never echoed: a partial or escaped copy would defeat redact().
        raise FetchError(
            f"The {env_name} value is not a single token: it holds spaces, line breaks "
            "or non-ASCII characters"
        )
    return value or None


def _safe_name(name: object, what: str = "file") -> str:
    if not isinstance(name, str) or not SAFE_NAME.fullmatch(name) or name.endswith(".part"):
        raise FetchError(f"Unsafe {what} name: {str(name)[:100]!r}")
    return name


def check_dest(dest: Path) -> Path:
    """dest must be a new or empty real directory; nothing is created here."""
    dest = Path(dest)
    if dest.is_symlink():
        raise FetchError(f"Destination is a symbolic link: {dest}")
    if dest.exists():
        if not dest.is_dir():
            raise FetchError(f"Destination is not a directory: {dest}")
        if any(dest.iterdir()):
            raise FetchError(f"Destination is not empty; choose a new directory: {dest}")
    return dest.absolute()


def make_dest(dest: Path) -> Path:
    dest = check_dest(dest)
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def sha256_file(path: Path) -> str:
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _require_space(directory: Path, needed: int) -> None:
    free = shutil.disk_usage(directory).free
    if needed > free:
        raise FetchError(f"Not enough disk space: need {needed} bytes, {free} free")


# ── Checksums ──────────────────────────────────────────────────────────────────


def is_checksum_name(name: str) -> bool:
    return name.lower() in {item.lower() for item in CHECKSUM_NAMES}


def parse_checksums(text: str) -> dict[str, str]:
    """`sha256sum` output: '<64 hex>  name' or '<64 hex> *name' per line."""
    entries: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([0-9A-Fa-f]{64}) [ *](\S.*)", line.rstrip("\r"))
        if match is None:
            raise FetchError(f"Malformed SHA256SUMS line {number}")
        digest, name = match[1].lower(), match[2]
        name = name[2:] if name.startswith("./") else name
        if entries.get(name, digest) != digest:
            raise FetchError(f"SHA256SUMS lists {name!r} twice with different digests")
        entries[name] = digest
    if not entries:
        raise FetchError("SHA256SUMS lists no files")
    return entries


def verify_checksums(digests: dict[str, str], sums: dict[str, str]) -> list[str]:
    """Every file must be listed with a matching digest (fail closed)."""
    for name, digest in sorted(digests.items()):
        if name not in sums:
            raise FetchError(f"No SHA256SUMS entry for {name}")
        if sums[name] != digest:
            raise FetchError(f"SHA-256 mismatch for {name}")
    return sorted(digests)


def _read_checksums(path: Path) -> dict[str, str]:
    if path.stat().st_size > MAX_CHECKSUM_BYTES:
        raise FetchError(f"Checksum file is too large: {path.name}")
    return parse_checksums(path.read_text(encoding="utf-8-sig"))


# ── Safe extraction ────────────────────────────────────────────────────────────


def archive_kind(name: str) -> tuple[str, str] | None:
    """('zip' or 'tar', stem) for a supported archive name, else None."""
    lower = name.lower()
    for suffix, kind in ARCHIVE_SUFFIXES:
        if lower.endswith(suffix) and len(name) > len(suffix):
            return kind, name[: -len(suffix)]
    return None


def member_parts(name: str) -> tuple[str, ...]:
    """Relative path components of an archive member; anything unsafe is refused."""
    shown = repr(name[:200])
    if not name or "\x00" in name or "\\" in name:
        raise FetchError(f"Unsafe archive member name: {shown}")
    if name.startswith("/") or re.match(r"[A-Za-z]:", name):
        raise FetchError(f"Absolute path in archive: {shown}")
    parts = tuple(part for part in name.split("/") if part not in ("", "."))
    if ".." in parts:
        raise FetchError(f"Parent-directory component in archive: {shown}")
    return parts


def _zip_members(archive: zipfile.ZipFile, limits: Limits) -> list[Member]:
    members = []
    for info in archive.infolist():
        shown = repr(info.filename[:200])
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise FetchError(f"Symbolic link in archive: {shown}")
        if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise FetchError(f"Special file in archive: {shown}")
        if info.flag_bits & 0x1:
            raise FetchError(f"Encrypted archive member: {shown}")
        if info.file_size > RATIO_FLOOR and (
            info.file_size > limits.max_ratio * max(info.compress_size, 1)
        ):
            raise FetchError(f"Compression ratio over {limits.max_ratio}: {shown}")
        is_dir = info.is_dir()
        members.append(Member(member_parts(info.filename), is_dir, 0 if is_dir else
                              info.file_size, info))
    return members


def _tar_members(archive: tarfile.TarFile) -> list[Member]:
    members = []
    for info in archive.getmembers():
        shown = repr(info.name[:200])
        if info.issym():
            raise FetchError(f"Symbolic link in archive: {shown}")
        if info.islnk():
            raise FetchError(f"Hard link in archive: {shown}")
        if info.ischr() or info.isblk() or info.isfifo():
            raise FetchError(f"Device or special file in archive: {shown}")
        if not (info.isreg() or info.isdir()):
            raise FetchError(f"Unsupported archive member type: {shown}")
        members.append(Member(member_parts(info.name), info.isdir(),
                              0 if info.isdir() else info.size, info))
    return members


def plan_members(members: list[Member], archive_bytes: int, limits: Limits) -> list[Member]:
    """Refuse duplicates, file/directory clashes, and size or ratio bombs."""
    if len(members) > limits.max_members:
        raise FetchError(f"Archive has more than {limits.max_members} members")
    kept = [m for m in members if m.parts and m.parts[0] not in SKIPPED_TOP_DIRS]
    files, directories = set(), set()
    for member in kept:
        target = directories if member.is_dir else files
        if member.parts in files or (not member.is_dir and member.parts in directories):
            raise FetchError(f"Duplicate archive member: {'/'.join(member.parts)!r}")
        target.add(member.parts)
    for parts in files:
        if any(parts[:index] in files for index in range(1, len(parts))):
            raise FetchError(f"Archive member is below a file: {'/'.join(parts)!r}")
    total = sum(member.size for member in kept)
    if total > limits.max_total_bytes:
        raise FetchError(
            f"Archive expands to {total} bytes, over the {limits.max_total_bytes}-byte limit"
        )
    if total > RATIO_FLOOR and total > limits.max_ratio * max(archive_bytes, 1):
        raise FetchError(f"Archive expands over {limits.max_ratio} times its size")
    return kept


def _copy_member(source, destination: Path, declared: int) -> int:
    copied = 0
    with source, open(destination, "xb") as output:
        while chunk := source.read(CHUNK):
            copied += len(chunk)
            if copied > declared:
                raise FetchError(f"Archive member is larger than declared: {destination.name}")
            output.write(chunk)
    if copied != declared:
        raise FetchError(f"Archive member is truncated: {destination.name}")
    return copied


def extract_archive(path: Path, target: Path, limits: Limits | None = None) -> dict:
    """Validate every member, then extract into the new directory target."""
    limits = limits or Limits()
    kind = archive_kind(path.name)
    if kind is None:
        raise FetchError(f"Not a supported archive: {path.name}")
    if target.exists() or target.is_symlink():
        raise FetchError(f"Extraction target already exists: {target}")
    archive_bytes = path.stat().st_size
    try:
        # Closed by the with block below.
        handle = (
            zipfile.ZipFile(path) if kind[0] == "zip"
            else tarfile.open(path, "r:*")  # noqa: SIM115
        )
    except ARCHIVE_ERRORS as exc:
        raise FetchError(f"Cannot read archive {path.name}: {exc}") from exc
    with handle:
        try:
            members = (
                _zip_members(handle, limits) if kind[0] == "zip" else _tar_members(handle)
            )
        except ARCHIVE_ERRORS as exc:
            raise FetchError(f"Cannot read archive {path.name}: {exc}") from exc
        kept = plan_members(members, archive_bytes, limits)
        total = sum(member.size for member in kept)
        _require_space(target.parent, total)
        target.mkdir()
        root = target.resolve()
        written = directories = 0
        try:
            for member in kept:
                destination = target.joinpath(*member.parts)
                if not destination.resolve().is_relative_to(root):
                    raise FetchError(f"Archive member escapes the target: {member.parts!r}")
                if member.is_dir:
                    destination.mkdir(parents=True, exist_ok=True)
                    directories += 1
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = (
                    handle.open(member.source) if kind[0] == "zip"
                    else handle.extractfile(member.source)
                )
                if source is None:
                    raise FetchError(f"Unreadable archive member: {'/'.join(member.parts)!r}")
                written += _copy_member(source, destination, member.size)
        except ARCHIVE_ERRORS as exc:
            shutil.rmtree(target, ignore_errors=True)
            raise FetchError(f"Corrupt archive {path.name}: {exc}") from exc
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
    return {
        "archive": path.name, "format": kind[0], "into": str(target),
        "files": sum(not member.is_dir for member in kept), "directories": directories,
        "bytes": written, "skipped_members": len(members) - len(kept),
    }


# ── Layout report ──────────────────────────────────────────────────────────────


def _read_data_yaml(yaml_path: Path) -> dict | None:
    """data.yaml as a mapping; None when it is too large or unreadable (reported, not fatal)."""
    try:
        if yaml_path.stat().st_size > MAX_YAML_BYTES:
            return None
        import yaml

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001 - an unreadable data.yaml is reported, not fatal
        return None
    return data if isinstance(data, dict) else None


def _class_names(data: dict | None) -> list[str] | None:
    """names as a list; a {index: name} mapping must use exactly the indices 0..n-1."""
    names = data.get("names") if data is not None else None
    if isinstance(names, dict):
        if set(names) != set(range(len(names))):
            return None
        names = [names[index] for index in range(len(names))]
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        return None
    return names


def _prepare_error(root: Path) -> str | None:
    """Why prepare_yolo_dataset.py would refuse this data.yaml, or None when it reads it."""
    try:
        if (root / "data.yaml").stat().st_size > MAX_YAML_BYTES:
            return "data.yaml is too large"
        prepare_names(root.resolve())
    except PreparationError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 - an unreadable data.yaml is reported, not fatal
        return f"data.yaml is unreadable ({type(exc).__name__})"
    return None


def _yaml_base(data: dict | None) -> str | None:
    base = data.get("path") if data is not None else None
    return None if base in (None, "") else str(base)


def _names_other_folder(root: Path, base: str | None) -> bool:
    """True when data.yaml path: is set and is not root, which train_finger_model.py refuses."""
    if base is None:
        return False
    try:
        base_path = Path(base)
        return not base_path.is_absolute() or base_path.resolve() != root.resolve()
    except (OSError, ValueError):
        return True


def describe_export(root: Path) -> dict:
    """A data.yaml directory: split counts, class names and whether it is prepared."""
    splits, missing = {}, []
    for split in SPLITS:
        images, labels = root / split / "images", root / split / "labels"
        if not images.is_dir() or not labels.is_dir():
            missing.append(split)
            continue
        image_stems = [
            path.stem for path in images.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ]
        label_stems = {path.stem for path in labels.glob("*.txt") if path.is_file()}
        splits[split] = {
            "images": len(image_stems), "labels": len(label_stems),
            "images_without_labels": sum(stem not in label_stems for stem in image_stems),
        }
    data = _read_data_yaml(root / "data.yaml")
    names = _class_names(data)
    prepared = (root / "manifest.json").is_file() and not missing
    kind = "incomplete" if not splits else "prepared" if prepared else "yolo_export"
    prepare_error = _prepare_error(root)
    base = _yaml_base(data)
    return {
        "path": str(root), "kind": kind,
        "roboflow": any(root.glob("README.roboflow*")),
        "splits": splits, "missing_splits": missing, "class_names": names,
        "matches_expected_classes": names is not None and len(names) == len(EXPECTED_NAMES)
        and set(names) == set(EXPECTED_NAMES),
        "expected_class_order": names == EXPECTED_NAMES,
        # prepare_yolo_dataset.py reads only an inline names: [...] line and nc: 12.
        "prepare_compatible": prepare_error is None, "prepare_error": prepare_error,
        # A prepared copy from another machine still names that machine's folder.
        "data_yaml_path": None if base is None else base[:300],
        "needs_relocation": kind == "prepared" and _names_other_folder(root, base),
    }


def detect_layout(dest: Path) -> dict:
    exports, weights = [], []
    for current, directories, files in os.walk(dest):
        here = Path(current)
        directories[:] = sorted(
            name for name in directories
            if name not in SKIPPED_TOP_DIRS and not (here / name).is_symlink()
        )
        if "data.yaml" in files and (here / "data.yaml").is_file():
            exports.append(describe_export(here))
        for name in sorted(files):
            path = here / name
            if name.lower().endswith(".pt") and path.is_file() and not path.is_symlink():
                weights.append({
                    "path": str(path), "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                })
    return {"yolo_exports": exports, "weights": weights}


def _free_path(dest: Path, name: str, taken: set[Path]) -> Path:
    candidate, number = dest / name, 2
    while candidate.exists() or candidate in taken:
        candidate, number = dest / f"{name}-{number}", number + 1
    taken.add(candidate)
    return candidate


def pick_weights(layout: dict) -> str | None:
    """The only .pt found, else the only best.pt among several, else None (placeholder)."""
    paths = [item["path"] for item in layout["weights"]]
    if len(paths) == 1:
        return paths[0]
    best = [path for path in paths if Path(path).name == "best.pt"]
    return best[0] if len(best) == 1 else None


def _report_name(data: Path, used: set[str]) -> str:
    """finger-count-<dataset>-valid.json, unique among the commands printed."""
    stem = re.sub(r"[^A-Za-z0-9._+-]+", "_", data.name).strip("._+-") or "dataset"
    name, number = f"finger-count-{stem}-valid.json", 2
    while name in used:
        name, number = f"finger-count-{stem}-{number}-valid.json", number + 1
    used.add(name)
    return name


def next_commands(dest: Path, layout: dict) -> list[str]:
    """Commands to run from backend/ with what was found."""
    quote = shlex.quote
    picked = pick_weights(layout)
    weights = quote(picked) if picked else WEIGHTS_PLACEHOLDER
    commands, taken, reports = [], set(), set()
    for export in layout["yolo_exports"]:
        if export["kind"] == "incomplete":
            continue
        if export["kind"] == "prepared":
            data = Path(export["path"])
        else:
            data = _free_path(dest, "prepared", taken)
            commands.append(
                f"python scripts/prepare_yolo_dataset.py --source {quote(export['path'])} "
                f"--output {quote(str(data))}"
            )
        commands.append(
            f"python scripts/evaluate_finger_count.py visible --weights {weights} "
            f"--split {quote(str(data / 'valid'))} --output {_report_name(data, reports)}"
        )
        commands.append(
            f"python scripts/train_finger_model.py --data {quote(str(data))} "
            f"--weights {weights} --dry-run"
        )
    if not commands:
        commands = [
            "python scripts/prepare_yolo_dataset.py --source <YOLO export with data.yaml> "
            "--output <new prepared dataset>",
            f"python scripts/evaluate_finger_count.py visible --weights {weights} "
            "--split <prepared dataset>/valid --output finger-count-valid.json",
            f"python scripts/train_finger_model.py --data <prepared dataset> "
            f"--weights {weights} --dry-run",
        ]
    return commands


def _weights_warning(layout: dict) -> str | None:
    paths = [item["path"] for item in layout["weights"]]
    if len(paths) < 2:
        return None
    shown = ", ".join(paths[:10]) + (f" and {len(paths) - 10} more" if len(paths) > 10 else "")
    picked = pick_weights(layout)
    used = (
        f"the commands use {picked}; check that it is the finger model" if picked
        else f"the commands show {WEIGHTS_PLACEHOLDER}: put the finger model's path there"
    )
    return f"Found {len(paths)} .pt files ({shown}); {used}."


def layout_warnings(layout: dict) -> list[str]:
    warnings = []
    if layout["weights"]:
        warnings.append("Weights are pickles: load them only from a source you trust.")
    if (weights_warning := _weights_warning(layout)) is not None:
        warnings.append(weights_warning)
    if not layout["yolo_exports"]:
        warnings.append("No YOLO export (data.yaml with train/valid/test) was found.")
    for export in layout["yolo_exports"]:
        path = export["path"]
        if export["kind"] == "incomplete":
            continue
        if export["kind"] == "yolo_export" and export["missing_splits"]:
            warnings.append(
                f"{path} lacks {'/'.join(export['missing_splits'])}: "
                "prepare_yolo_dataset.py needs train, valid and test."
            )
        if not export["matches_expected_classes"]:
            warnings.append(
                f"{path} does not have the 12 cultivar/ripeness classes "
                "that prepare_yolo_dataset.py expects."
            )
        elif not export["expected_class_order"]:
            warnings.append(
                f"{path} lists the 12 classes in another order: prepare_yolo_dataset.py keeps "
                "it, and train_finger_model.py refuses any order but "
                "prepare_yolo_dataset.EXPECTED_NAMES."
            )
        # Wrong classes already have a warning; this catches the form prepare cannot read.
        if (
            export["kind"] == "yolo_export" and export["matches_expected_classes"]
            and not export["prepare_compatible"]
        ):
            warnings.append(
                f"{path}/data.yaml is not in the form prepare_yolo_dataset.py reads "
                f"({export['prepare_error']}): it needs an inline names: [...] line and nc: 12."
            )
        if export["needs_relocation"]:
            warnings.append(
                f"{path}/data.yaml path: names {export['data_yaml_path']!r}, not this folder "
                f"(a copy moved from another machine): set path: to {path} or remove the "
                "line before running train_finger_model.py (prepare_ood_dataset.py "
                "merge-negatives also writes a relocated copy)."
            )
    return warnings


# ── Shared tail: verify, extract, report ───────────────────────────────────────


def _remove(dest: Path, names: Iterable[str]) -> None:
    for name in names:
        (dest / name).unlink(missing_ok=True)


def unpack_downloads(
    dest: Path, digests: dict[str, str], *, require_checksums: bool, limits: Limits
) -> dict:
    """Verify the flat files in dest against SHA256SUMS, then extract the archives."""
    sums_names = [name for name in digests if is_checksum_name(name)]
    payload = {name: digest for name, digest in digests.items() if name not in sums_names}
    checksums = None
    try:
        if len(sums_names) > 1:
            raise FetchError(f"More than one checksum file: {sorted(sums_names)}")
        if sums_names:
            sums = _read_checksums(dest / sums_names[0])
            checksums = {
                "file": sums_names[0], "verified": verify_checksums(payload, sums),
                "entries_not_downloaded": sorted(set(sums) - set(payload)),
            }
        elif require_checksums:
            raise FetchError("No SHA256SUMS asset; refusing unverified downloads")
    except BaseException:
        _remove(dest, digests)
        raise
    archives = {name: archive_kind(name) for name in payload if archive_kind(name)}
    stems = [kind[1] for kind in archives.values()]
    for stem in stems:
        if stems.count(stem) > 1 or stem in digests:
            raise FetchError(f"Two downloads would extract into {stem}/")
    extracted = [
        extract_archive(dest / name, dest / kind[1], limits)
        for name, kind in sorted(archives.items())
    ]
    layout = detect_layout(dest)
    warnings = [] if checksums is not None else [
        "No SHA256SUMS: downloads were not verified; compare the sha256 values "
        "with the publisher."
    ]
    return {
        "checksums": checksums, "extracted": extracted, "layout": layout,
        "next_commands": next_commands(dest, layout),
        "warnings": warnings + layout_warnings(layout),
    }


# ── GitHub ─────────────────────────────────────────────────────────────────────


class HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects (asset downloads go to a signed storage URL) only over HTTPS.

    The token is an unredirected header, so it never travels with a redirect.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise FetchError("Refused a redirect that leaves HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_opener():
    return urllib.request.build_opener(
        HttpsOnlyRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context())
    )


def api_request(url: str, token: str | None, accept: str) -> urllib.request.Request:
    request = urllib.request.Request(url, headers={
        "Accept": accept, "User-Agent": USER_AGENT, "X-GitHub-Api-Version": "2022-11-28",
    })
    if token:
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    return request


def _http_hint(code: int, what: str, authenticated: bool) -> str:
    message = f"GitHub returned HTTP {code} for {what}"
    if code in (401, 403, 404) and not authenticated:
        message += "; a private repository needs a token in the --token-env variable"
    elif code in (401, 403):
        message += "; check that the token can read this repository's releases"
    elif code == 404:
        message += "; check --repo and --tag"
    return message


def _open(opener, request: urllib.request.Request, what: str, token: str | None):
    try:
        response = opener.open(request, timeout=TIMEOUT_SECONDS)
    except urllib.error.HTTPError as exc:
        with contextlib.suppress(Exception):
            exc.close()
        # Nothing from the error (body, headers, request) is kept or chained.
        raise FetchError(_http_hint(exc.code, what, bool(token))) from None
    except urllib.error.URLError as exc:
        reason = redact(str(exc.reason), token)
        raise FetchError(f"Cannot reach GitHub for {what}: {reason}") from None
    except FetchError:
        raise
    except Exception as exc:  # noqa: BLE001 - its text may hold the request's headers
        raise FetchError(f"Cannot reach GitHub for {what} ({type(exc).__name__})") from None
    status = getattr(response, "status", 200)
    if status != 200:
        response.close()
        raise FetchError(f"GitHub returned HTTP {status} for {what}")
    return response


def _read(response, size: int, what: str) -> bytes:
    try:
        return response.read(size)
    except (http.client.HTTPException, OSError) as exc:
        raise FetchError(f"Download of {what} was cut off ({type(exc).__name__})") from None


def _content_length(response) -> int | None:
    value = response.headers.get("Content-Length")
    return int(value) if value is not None and str(value).isdigit() else None


def release_assets(
    repo: str, tag: str, token: str | None, opener
) -> list[dict]:
    url = f"{API_ROOT}/repos/{repo}/releases/tags/{urllib.parse.quote(tag, safe='')}"
    what = f"release {tag} of {repo}"
    request = api_request(url, token, "application/vnd.github+json")
    with _open(opener, request, what, token) as response:
        body = _read(response, MAX_METADATA_BYTES + 1, what)
    if len(body) > MAX_METADATA_BYTES:
        raise FetchError("Release metadata is too large")
    try:
        release = json.loads(body)
    except (ValueError, RecursionError):
        raise FetchError("Release metadata is not JSON") from None
    if not isinstance(release, dict) or not isinstance(release.get("assets"), list):
        raise FetchError("Release metadata has no asset list")
    # GitHub matches OWNER/NAME in any case and follows renames; its answer names the
    # repository as it is now, so the release's own api.github.com URL is accepted too.
    allowed = {repo.lower()}
    own = release.get("url")
    if isinstance(own, str) and (match := RELEASE_URL.fullmatch(own)) and _plain_repo(match[1]):
        allowed.add(match[1].lower())
    assets, names = [], set()
    for item in release["assets"]:
        if not isinstance(item, dict):
            raise FetchError("Malformed release asset")
        name = _safe_name(item.get("name"), "asset")
        url, size = item.get("url"), item.get("size")
        # The token goes only to this repository's asset API on api.github.com.
        match = ASSET_URL.fullmatch(url) if isinstance(url, str) else None
        if match is None or match[1].lower() not in allowed:
            raise FetchError(f"Unexpected download URL for asset {name}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise FetchError(f"Missing size for asset {name}")
        if name in names:
            raise FetchError(f"Duplicate asset name: {name}")
        names.add(name)
        assets.append({"name": name, "url": url, "size": size})
    return assets


def select_assets(assets: list[dict], patterns: Sequence[str]) -> list[dict]:
    if not patterns:
        selected = list(assets)
    else:
        selected = [
            asset for asset in assets if is_checksum_name(asset["name"])
            or any(fnmatch.fnmatchcase(asset["name"], pattern) for pattern in patterns)
        ]
    if not any(not is_checksum_name(asset["name"]) for asset in selected):
        raise FetchError("No release asset to download" + (
            f" matches {list(patterns)}" if patterns else ""
        ))
    return selected


def download_asset(
    asset: dict, dest: Path, token: str | None, opener
) -> str:
    """Stream one asset to dest/<name>; returns its SHA-256."""
    name, size = asset["name"], asset["size"]
    part = dest / f".{name}.part"
    digest, received = hashlib.sha256(), 0
    try:
        request = api_request(asset["url"], token, "application/octet-stream")
        with _open(opener, request, f"asset {name}", token) as response:
            declared = _content_length(response)
            if declared is not None and declared != size:
                raise FetchError(f"Asset {name} has {declared} bytes, the release says {size}")
            with open(part, "xb") as output:
                while chunk := _read(response, CHUNK, f"asset {name}"):
                    received += len(chunk)
                    if received > size:
                        raise FetchError(f"Asset {name} is larger than the release says")
                    digest.update(chunk)
                    output.write(chunk)
        if received != size:
            raise FetchError(f"Incomplete download of {name}: {received} of {size} bytes")
        os.replace(part, dest / name)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return digest.hexdigest()


def download_with_api(
    repo: str, tag: str, dest: Path, patterns: Sequence[str], token: str | None, opener
) -> dict[str, str]:
    assets = select_assets(release_assets(repo, tag, token, opener), patterns)
    _require_space(dest, sum(asset["size"] for asset in assets))
    digests: dict[str, str] = {}
    try:
        for asset in assets:
            digests[asset["name"]] = download_asset(asset, dest, token, opener)
    except BaseException:
        _remove(dest, digests)
        raise
    return digests


def run_command(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - list arguments, no shell
        command, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        check=False,
    )


def any_case_glob(name: str) -> str:
    """A glob for name in any letter case ('[sS][hH][aA]256...'): gh globs are case-sensitive."""
    return "".join(f"[{char.lower()}{char.upper()}]" if char.isalpha() else char for char in name)


CHECKSUM_GLOBS = tuple(dict.fromkeys(any_case_glob(name.lower()) for name in CHECKSUM_NAMES))


def _clear(dest: Path) -> None:
    """Remove what gh wrote: dest was new or empty before it ran (make_dest checks that)."""
    for entry in dest.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink(missing_ok=True)


def download_with_gh(
    gh: str, repo: str, tag: str, dest: Path, patterns: Sequence[str], token: str | None,
    runner: Runner,
) -> dict[str, str]:
    command = [gh, "release", "download", tag, f"--repo={repo}", f"--dir={dest}"]
    if patterns:
        # Every name is_checksum_name() accepts, as on the API path.
        command += [f"--pattern={pattern}" for pattern in (*patterns, *CHECKSUM_GLOBS)]
    env = {**os.environ, "GH_PROMPT_DISABLED": "1"}
    if token:
        env["GH_TOKEN"] = token  # environment only: never an argument
    try:
        result = runner(command, env)
        if result.returncode == GH_AUTH_REQUIRED:
            raise GhAuthRequiredError(
                "gh is not logged in; run gh auth login, set the --token-env variable "
                "or rerun with --method api"
            )
        if result.returncode != 0:
            lines = (result.stderr or "").strip().splitlines()
            # Redact before cutting: a cut through the token would leave a prefix unmatched.
            detail = redact(lines[-1], token)[:300] if lines else "no error output"
            raise FetchError(
                f"gh release download failed with exit code {result.returncode}: {detail} "
                "(--method api uses the GitHub REST API instead)"
            )
        digests = {}
        for path in sorted(dest.iterdir()):
            if path.is_symlink() or not path.is_file():
                raise FetchError(f"gh left an unexpected entry in the destination: {path.name}")
            digests[_safe_name(path.name, "asset")] = sha256_file(path)
        if not any(not is_checksum_name(name) for name in digests):
            raise FetchError("No release asset was downloaded")
    except BaseException:
        _clear(dest)
        raise
    return digests


def _plain_repo(repo: str) -> bool:
    return bool(REPO.fullmatch(repo)) and ".." not in repo and not repo.endswith("/.")


def _validate_release(repo: str, tag: str, patterns: Sequence[str]) -> None:
    if not _plain_repo(repo):
        raise FetchError("--repo must be OWNER/NAME")
    if not TAG.fullmatch(tag) or ".." in tag:
        raise FetchError("--tag is not a valid release tag")
    for pattern in patterns:
        if not pattern or "/" in pattern or len(pattern) > 255 or pattern.startswith("-"):
            raise FetchError(f"Invalid --asset pattern: {pattern!r}")


def fetch_github(
    repo: str, tag: str, dest: Path, *, patterns: Sequence[str] = (), token: str | None = None,
    token_env: str = "GITHUB_TOKEN", method: str = "auto", require_checksums: bool = False,
    opener=None, runner: Runner | None = None, which: Callable[[str], str | None] = shutil.which,
    limits: Limits | None = None,
) -> dict:
    _validate_release(repo, tag, patterns)
    dest = make_dest(dest)
    gh = which("gh") if method in ("auto", "gh") else None
    if method == "gh" and gh is None:
        raise FetchError("The gh CLI is not installed; use --method api")
    digests, used, notes = None, "api", []
    if gh:
        try:
            digests = download_with_gh(gh, repo, tag, dest, patterns, token, runner or run_command)
            used = "gh"
        except GhAuthRequiredError:
            if method == "gh":
                raise
            # A public release needs no login: the REST API can still fetch it.
            notes.append("gh is not logged in, so the GitHub REST API was used instead.")
    if digests is None:
        digests = download_with_api(repo, tag, dest, patterns, token, opener or default_opener())
    files = [
        {"name": name, "bytes": (dest / name).stat().st_size, "sha256": digest}
        for name, digest in sorted(digests.items())
    ]
    tail = unpack_downloads(
        dest, digests, require_checksums=require_checksums, limits=limits or Limits()
    )
    tail["warnings"] = notes + tail["warnings"]
    return {
        "mode": "github", "fetched_at": now_manila().isoformat(timespec="seconds"),
        "dest": str(dest),
        "source": {
            "repo": repo, "tag": tag, "method": used, "asset_patterns": list(patterns),
            "token_env": token_env, "authenticated": bool(token),
        },
        "files": files, **tail,
    }


# ── Local file ─────────────────────────────────────────────────────────────────


def fetch_local(
    archive: Path, dest: Path, *, sha256: str | None = None, checksums: Path | None = None,
    limits: Limits | None = None,
) -> dict:
    archive = Path(archive)
    if not archive.is_file():
        raise FetchError(f"Archive not found: {archive}")
    # A chat attachment may be called "export (1).zip": only the copy's name is cleaned.
    name = re.sub(r"[^A-Za-z0-9._+-]+", "_", archive.name).lstrip("._-+")
    name = _safe_name(name or "archive")
    kind = archive_kind(name)
    if kind is None and not name.lower().endswith(".pt"):
        raise FetchError("--archive must be a .zip, .tar(.gz/.bz2/.xz), .tgz or .pt file")
    dest = check_dest(dest)
    digest = sha256_file(archive)
    verified = []
    if sha256 is not None:
        if not re.fullmatch(r"[0-9A-Fa-f]{64}", sha256):
            raise FetchError("--sha256 must be 64 hexadecimal digits")
        if sha256.lower() != digest:
            raise FetchError(f"SHA-256 mismatch for {archive.name}")
        verified.append("--sha256")
    if checksums is not None:
        verify_checksums({archive.name: digest}, _read_checksums(Path(checksums)))
        verified.append(Path(checksums).name)
    dest = make_dest(dest)
    limits = limits or Limits()
    if kind:
        extracted = [extract_archive(archive, dest / kind[1], limits)]
    else:
        _require_space(dest, archive.stat().st_size)
        shutil.copyfile(archive, dest / name)
        if sha256_file(dest / name) != digest:
            (dest / name).unlink()
            raise FetchError(f"Copy of {name} does not match the source")
        extracted = []
    layout = detect_layout(dest)
    warnings = [] if verified else [
        "Not verified: give --sha256 or --checksums to check the file before use."
    ]
    return {
        "mode": "local", "fetched_at": now_manila().isoformat(timespec="seconds"),
        "dest": str(dest),
        "source": {"archive": str(archive.absolute())},
        "files": [{"name": archive.name, "bytes": archive.stat().st_size, "sha256": digest}],
        "checksums": {"verified_by": verified} if verified else None,
        "extracted": extracted, "layout": layout,
        "next_commands": next_commands(dest, layout),
        "warnings": warnings + layout_warnings(layout),
    }


# ── Command line ───────────────────────────────────────────────────────────────


def main(
    argv: list[str] | None = None, *, opener=None, runner: Runner | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    github = commands.add_parser("github", help="download the assets of a GitHub release")
    github.add_argument("--repo", required=True, help="OWNER/NAME")
    github.add_argument("--tag", required=True, help="release tag")
    github.add_argument("--dest", type=Path, required=True, help="new or empty directory")
    github.add_argument("--asset", action="append", default=[], metavar="PATTERN",
                        help="glob of asset names to download (repeatable; default: all)")
    github.add_argument("--token-env", default="GITHUB_TOKEN",
                        help="environment variable that holds a token (value never printed)")
    github.add_argument("--method", choices=("auto", "gh", "api"), default="auto",
                        help="gh CLI or REST API (default: gh when installed)")
    github.add_argument("--require-checksums", action="store_true",
                        help="refuse a release without a SHA256SUMS asset")
    local = commands.add_parser("local", help="verify and unpack a file already on disk")
    local.add_argument("--archive", type=Path, required=True,
                       help=".zip, .tar(.gz/.bz2/.xz), .tgz or .pt file")
    local.add_argument("--dest", type=Path, required=True, help="new or empty directory")
    local.add_argument("--sha256", help="expected SHA-256 of the archive")
    local.add_argument("--checksums", type=Path, help="SHA256SUMS file that lists the archive")
    args = parser.parse_args(argv)
    token = None
    try:
        if args.command == "github":
            token = read_token(args.token_env)
            report = fetch_github(
                args.repo, args.tag, args.dest, patterns=args.asset, token=token,
                token_env=args.token_env, method=args.method,
                require_checksums=args.require_checksums, opener=opener, runner=runner,
                which=which,
            )
        else:
            report = fetch_local(
                args.archive, args.dest, sha256=args.sha256, checksums=args.checksums
            )
    except (OSError, ValueError) as exc:
        parser.exit(2, redact(f"Fetch failed: {exc}\n", token))
    print(redact(json.dumps(report, indent=2), token))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
