"""Remove old system flags that the current auto-flag rule would not set.

Rule (2026-11-18): a scan is flagged automatically only when its confidence is below the
review threshold saved in System Configuration. Before that date the system also flagged
scans for different finger counts between cameras, camera disagreements, missing captures
and dropped boxes, so Scan Logs and Quality Control still show those scans as Flagged.

Run on the station PC, from the backend folder, with the station's own Python:

    cd C:\\BananaVision\\backend
    .\\venv\\Scripts\\python.exe scripts\\review_auto_flags.py
        Preview only. Lists every flagged scan and what would happen. Changes nothing.

    .\\venv\\Scripts\\python.exe scripts\\review_auto_flags.py --apply --admin <username>
        Removes the flags listed as "remove flag". <username> is the administrator who
        takes responsibility; each change is written to Scan History and the Activity Log
        under that account.

A flag is kept whenever a person may have decided it, or the data cannot show otherwise:
  * the confidence is below the threshold (the rule still flags it);
  * a person flagged, corrected or wrote a note on the scan;
  * a person sent a flag or change request that changed nothing. "Flag for Review" on a
    scan the system had already flagged is recorded only this way;
  * the scan has no creation record (scans from before scan history existed), so who
    flagged it is unknown;
  * no confidence is stored for the scan.

The command reads the database settings the backend uses (backend/.env), so it must be
started in the backend folder. It prints only scan identifiers, dates, labels and
confidence. It can run while the backend is running; reload open BananaVision pages
afterwards. It waits while a backup or restore is running.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from types import SimpleNamespace  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.core.time import as_manila  # noqa: E402
from app.models import (  # noqa: E402
    Intake,
    Scan,
    ScanClassification,
    ScanEvent,
    ScanMutation,
    ScanNote,
    SystemConfig,
    UserAccount,
)
from app.schemas.enums import ActiveStatusEnum, RoleEnum  # noqa: E402
from app.services import scan_records  # noqa: E402

logger = logging.getLogger("bananavision.review_auto_flags")

# History entries that record a person's decision about the scan.
PERSON_EVENTS = ("flag", "correction", "note")
HANDLED = "A person flagged, corrected or noted this scan"
UNRECORDED = (
    "A person sent a flag or change request that changed nothing "
    "(for example Flag for Review on an already flagged scan)"
)
UNKNOWN_ORIGIN = "This scan has no creation record, so who flagged it is unknown"
NO_CONFIDENCE = "No confidence is stored for this scan"
# A request and the history entry it wrote are saved in one transaction, moments apart.
SAME_REQUEST = timedelta(seconds=5)


class CleanupError(Exception):
    """The command cannot continue; the message is safe to show."""


@dataclass(frozen=True)
class Decision:
    scan_id: object
    scanned_at: object
    label: str
    confidence: float | None
    action: str  # "remove" or "keep"
    reason: str


@dataclass
class Report:
    threshold: int
    applied: bool
    decisions: list[Decision] = field(default_factory=list)
    removed: int = 0
    skipped: int = 0
    admin: str | None = None


def _percent(value: float) -> str:
    return f"{float(value):g}"


def _decide(confidence, person_reason: str | None, threshold: int) -> tuple[str, str]:
    """The current rule applied to one stored scan; a person's decision always wins."""
    if person_reason:
        return "keep", person_reason
    if confidence is None:
        return "keep", NO_CONFIDENCE
    if float(confidence) < threshold:
        return "keep", f"Confidence {_percent(confidence)}% is below the {threshold}% threshold"
    return "remove", f"Confidence {_percent(confidence)}% is not below the {threshold}% threshold"


def _value(item) -> str:
    return str(getattr(item, "value", item) or "Unknown")


def _label(cultivar, ripeness) -> str:
    return f"{_value(cultivar)} {_value(ripeness)}"


async def _threshold(db) -> int:
    """The saved review threshold, read without writing: the canonical row, else the newest."""
    saved = await db.scalar(
        select(SystemConfig.confidence_threshold).where(SystemConfig.canonical_key == 1)
    )
    if saved is None:
        saved = await db.scalar(
            select(SystemConfig.confidence_threshold)
            .order_by(SystemConfig.updated_at.desc(), SystemConfig.id.desc()).limit(1)
        )
    if saved is None:
        raise CleanupError(
            "No saved System Configuration was found. Open System Config in the app once, "
            "then run this command again."
        )
    return int(saved)


async def _person_reasons(db, only=None) -> dict:
    """Why each flagged scan (or the one given) is left to people: scan id -> reason.

    A flagged scan absent from the result was flagged by the system and nobody decided
    anything about it since.
    """
    flagged = select(Scan.id).where(Scan.flagged.is_(True))
    if only is not None:
        flagged = flagged.where(Scan.id == only)

    overridden = set((await db.execute(
        select(Scan.id).where(Scan.id.in_(flagged), Scan.is_overridden.is_(True))
    )).scalars().all())
    noted = set((await db.execute(
        select(ScanNote.scan_id).where(ScanNote.scan_id.in_(flagged)).distinct()
    )).scalars().all())
    events: dict = {}
    for scan_id, revision, kind, actor_id, timestamp in (await db.execute(
        select(ScanEvent.scan_id, ScanEvent.revision, ScanEvent.kind, ScanEvent.actor_id,
               ScanEvent.timestamp).where(ScanEvent.scan_id.in_(flagged))
    )).all():
        events.setdefault(scan_id, []).append((revision, kind, actor_id, timestamp))
    scan_ids = set((await db.execute(flagged)).scalars().all())

    # A request that changed nothing wrote a receipt but no history entry. The receipt
    # answers with the scan as it was, so its revision points at an older entry.
    scan_field = ScanMutation.response["id"].as_string()
    receipts = select(ScanMutation.actor_id, ScanMutation.created_at, scan_field,
                      ScanMutation.response["revision"].as_integer())
    if only is not None:
        receipts = receipts.where(scan_field == str(only))
    by_text = {str(scan_id): scan_id for scan_id in scan_ids}
    unrecorded = set()
    for actor_id, created_at, scan_text, revision in (await db.execute(receipts)).all():
        scan_id = by_text.get(scan_text)
        if scan_id is None:
            continue
        wrote_entry = any(
            entry_revision == revision and kind != "created" and entry_actor == actor_id
            and abs(as_manila(timestamp) - as_manila(created_at)) <= SAME_REQUEST
            for entry_revision, kind, entry_actor, timestamp in events.get(scan_id, [])
        )
        if not wrote_entry:
            unrecorded.add(scan_id)

    reasons = {}
    for scan_id in scan_ids:
        kinds = {kind for _, kind, _, _ in events.get(scan_id, [])}
        if kinds & set(PERSON_EVENTS) or scan_id in overridden or scan_id in noted:
            reasons[scan_id] = HANDLED
        elif scan_id in unrecorded:
            reasons[scan_id] = UNRECORDED
        elif "created" not in kinds:
            reasons[scan_id] = UNKNOWN_ORIGIN
    return reasons


def _active_admin(account) -> bool:
    role = getattr(getattr(account, "role", None), "name", None)
    return (account is not None and account.status == ActiveStatusEnum.ACTIVE
            and role == RoleEnum.ADMIN.value)


async def _administrator(db, username: str | None):
    if not username:
        raise CleanupError("--apply needs --admin <username> (the administrator responsible)")
    account = (await db.execute(
        select(UserAccount).options(selectinload(UserAccount.role))
        .where(UserAccount.username == username)
    )).scalar_one_or_none()
    if not _active_admin(account):
        raise CleanupError(f"No active administrator account is named '{username}'")
    # A plain copy: the account object expires with each transaction of this command.
    return SimpleNamespace(id=account.id, username=account.username,
                           full_name=account.full_name)


async def _remove_flag(db, scan_id, admin, threshold: int) -> bool:
    """Un-flag one scan under its row locks, if the decision still holds. Commits or rolls back."""
    # Same lock order as every scan change in the app: account, then intake, then scan.
    account = (await db.execute(
        select(UserAccount).options(selectinload(UserAccount.role))
        .where(UserAccount.id == admin.id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if not _active_admin(account):
        await db.rollback()
        raise CleanupError(f"'{admin.username}' is no longer an active administrator; stopped")
    intake_id = await db.scalar(select(Scan.intake_id).where(Scan.id == scan_id))
    if intake_id is not None:
        await db.execute(select(Intake.id).where(Intake.id == intake_id).with_for_update())
    scan = (await db.execute(
        select(Scan).where(Scan.id == scan_id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    confidence = scan.classification.confidence if scan and scan.classification else None
    person_reason = (await _person_reasons(db, only=scan_id)).get(scan_id) if scan else None
    if (scan is None or not scan.flagged
            or _decide(confidence, person_reason, threshold)[0] != "remove"):
        await db.rollback()
        return False
    await scan_records.apply_scan_change(
        db, scan, admin, "flag", {"flagged": False},
        reason=(
            "Auto-flag rule corrected: only a confidence below the threshold flags a scan "
            f"({_percent(confidence)}% is not below {threshold}%)"
        ),
    )
    await db.commit()
    return True


async def review(sessions, *, apply: bool = False, admin_username: str | None = None) -> Report:
    """List every flagged scan with its decision; with ``apply`` remove the flags to remove."""
    async with sessions() as db:
        threshold = await _threshold(db)
        admin = await _administrator(db, admin_username) if apply else None
        # Only the columns the decision needs; no scan graph is loaded for the listing.
        rows = (await db.execute(
            select(Scan.id, Scan.date_time, ScanClassification.cultivar,
                   ScanClassification.ripeness, ScanClassification.confidence)
            .outerjoin(ScanClassification, ScanClassification.scan_id == Scan.id)
            .where(Scan.flagged.is_(True)).order_by(Scan.date_time, Scan.id)
        )).all()
        person_reasons = await _person_reasons(db)
        report = Report(threshold=threshold, applied=apply,
                        admin=admin.username if admin else None)
        for scan_id, scanned_at, cultivar, ripeness, confidence in rows:
            action, reason = _decide(confidence, person_reasons.get(scan_id), threshold)
            report.decisions.append(Decision(
                scan_id=scan_id, scanned_at=scanned_at, label=_label(cultivar, ripeness),
                confidence=float(confidence) if confidence is not None else None,
                action=action, reason=reason,
            ))
        await db.rollback()  # the listing holds no transaction open
        if not apply:
            return report
        for decision in report.decisions:
            if decision.action != "remove":
                continue
            # One short transaction per scan: a problem with one scan cannot undo the others.
            try:
                removed = await _remove_flag(db, decision.scan_id, admin, threshold)
            except CleanupError:
                raise
            except Exception as error:  # a database error on this scan only
                await db.rollback()
                logger.error("Scan %s was left flagged: %s", decision.scan_id,
                             type(error).__name__)
                removed = False
            if removed:
                report.removed += 1
            else:
                report.skipped += 1
    return report


def render(report: Report) -> str:
    remove = [item for item in report.decisions if item.action == "remove"]
    keep = [item for item in report.decisions if item.action == "keep"]
    lines = [
        "BananaVision auto-flag review",
        f"Rule: a scan is flagged only when its confidence is below {report.threshold}% "
        "(System Configuration).",
        "",
    ]
    if report.applied:
        lines.append(
            f"APPLIED by {report.admin}: {report.removed} "
            f"flag{'' if report.removed == 1 else 's'} removed."
        )
        if report.skipped:
            one = report.skipped == 1
            lines.append(
                f"{report.skipped} scan{'' if one else 's'} could not be changed (changed "
                f"while the command ran, or a database error) and "
                f"{'was' if one else 'were'} left flagged."
            )
        lines.append("Reload open BananaVision pages to see the change.")
    else:
        lines.append("PREVIEW: nothing was changed.")
        lines.append("To remove the flags listed as 'remove flag', run again with "
                     "--apply --admin <username>.")
    lines += [
        "",
        f"Flagged scans: {len(report.decisions)}",
        f"  remove flag: {len(remove)}",
        f"  keep flag: {len(keep)}",
        "",
    ]
    if report.decisions:
        lines.append(f"{'Scanned (Asia/Manila)':<22}{'Scan ID':<38}{'Result':<24}"
                     f"{'Conf.':<8}Decision")
        for item in report.decisions:
            when = as_manila(item.scanned_at).strftime("%Y-%m-%d %H:%M")
            confidence = "-" if item.confidence is None else f"{_percent(item.confidence)}%"
            decision = "remove flag" if item.action == "remove" else "keep flag"
            lines.append(f"{when:<22}{str(item.scan_id):<38}{item.label:<24}"
                         f"{confidence:<8}{decision}: {item.reason}")
    return "\n".join(lines)


def default_sessions():
    """The backend's own session factory; honours a running backup or restore.

    The backend reads backend/.env from the current folder. Started anywhere else, the
    settings would fall back to defaults and could point at a different database.
    """
    if Path.cwd().resolve() != BACKEND:
        raise CleanupError(
            f"Run this command from the backend folder, so it uses the station's settings: "
            f"cd \"{BACKEND}\""
        )
    from app.core.database import async_session_factory
    from app.services import maintenance_database  # noqa: F401 - registers the shared lock

    return async_session_factory


async def _run(arguments) -> Report:
    sessions = default_sessions()
    try:
        return await review(sessions, apply=arguments.apply, admin_username=arguments.admin)
    finally:
        # Close the connection pool this command opened, when it opened one.
        engine = getattr(sessions, "kw", {}).get("bind")
        if engine is not None:
            await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove old system flags that the confidence-only rule would not set. "
                    "Preview by default.",
    )
    parser.add_argument("--apply", action="store_true",
                        help="remove the flags; without this option nothing is changed")
    parser.add_argument("--admin", metavar="USERNAME",
                        help="administrator responsible for the change (needed with --apply)")
    arguments = parser.parse_args(argv)
    try:
        if arguments.apply and not arguments.admin:
            raise CleanupError("--apply needs --admin <username> (the administrator responsible)")
        report = asyncio.run(_run(arguments))
    except CleanupError as error:
        print(f"Not done: {error}", file=sys.stderr)
        return 2
    except (OSError, SQLAlchemyError) as error:
        # Never print the connection settings; the error type is enough to act on.
        print(f"Not done: the database could not be reached or answered with an error "
              f"({type(error).__name__}). Check that PostgreSQL is running and that this "
              f"command was started in the backend folder.", file=sys.stderr)
        return 2
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
