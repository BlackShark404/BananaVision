"""Remove old system flags that the current auto-flag rule would not set.

Rule (2026-11-18): a scan is flagged automatically only when its confidence is below the
review threshold saved in System Configuration. Before that date the system also flagged
scans for different finger counts between cameras, camera disagreements, missing captures
and dropped boxes, so Scan Logs and Quality Control still show those scans as Flagged.

Run on the station PC, from the backend folder, with the station's own Python:

    .\\venv\\Scripts\\python.exe scripts\\review_auto_flags.py
        Preview only. Lists every flagged scan and what would happen. Changes nothing.

    .\\venv\\Scripts\\python.exe scripts\\review_auto_flags.py --apply --admin <username>
        Removes the flags listed as "remove flag". <username> is the administrator who
        takes responsibility; each change is written to Scan History and the Activity Log
        under that account.

What is never touched:
  * a scan whose confidence is below the threshold (the rule still flags it);
  * a scan a person flagged, corrected or wrote a note on (a person already decided);
  * a scan with no stored confidence.

The command reads the database settings the backend uses (backend/.env) and prints only
scan identifiers, dates, labels and confidence. It can run while the backend is running;
reload open BananaVision pages afterwards. It waits while a backup or restore is running.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from types import SimpleNamespace  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.core.time import as_manila  # noqa: E402
from app.models import (  # noqa: E402
    Intake,
    Scan,
    ScanClassification,
    ScanEvent,
    SystemConfig,
    UserAccount,
)
from app.schemas.enums import ActiveStatusEnum, RoleEnum  # noqa: E402
from app.services import scan_records  # noqa: E402

# A person made a decision about the scan; the command leaves it to people.
PERSON_EVENTS = ("flag", "correction", "note")
HANDLED = "A person flagged, corrected or noted this scan"
NO_CONFIDENCE = "No confidence is stored for this scan"


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


def _decide(confidence, handled: bool, threshold: int) -> tuple[str, str]:
    """The current rule applied to one stored scan."""
    if handled:
        return "keep", HANDLED
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


async def _handled_scan_ids(db, scan_id=None) -> set:
    """Flagged scans (or the one given) that carry a person's flag, correction or note."""
    scope = (
        ScanEvent.scan_id == scan_id if scan_id is not None
        else ScanEvent.scan_id.in_(select(Scan.id).where(Scan.flagged.is_(True)))
    )
    rows = await db.execute(
        select(ScanEvent.scan_id).where(scope, ScanEvent.kind.in_(PERSON_EVENTS)).distinct()
    )
    return set(rows.scalars().all())


async def _administrator(db, username: str | None):
    if not username:
        raise CleanupError("--apply needs --admin <username> (the administrator responsible)")
    account = (await db.execute(
        select(UserAccount).options(selectinload(UserAccount.role))
        .where(UserAccount.username == username)
    )).scalar_one_or_none()
    role = getattr(getattr(account, "role", None), "name", None)
    if account is None or account.status != ActiveStatusEnum.ACTIVE or role != RoleEnum.ADMIN.value:
        raise CleanupError(f"No active administrator account is named '{username}'")
    # A plain copy: the account object expires with each transaction of this command.
    return SimpleNamespace(id=account.id, username=account.username,
                           full_name=account.full_name)


async def _remove_flag(db, scan_id, admin, threshold: int) -> bool:
    """Un-flag one scan under its row lock, if the decision still holds. Commits or rolls back."""
    intake_id = await db.scalar(select(Scan.intake_id).where(Scan.id == scan_id))
    if intake_id is not None:
        # Same parent-first lock order as every other scan change.
        await db.execute(select(Intake.id).where(Intake.id == intake_id).with_for_update())
    scan = (await db.execute(
        select(Scan).where(Scan.id == scan_id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    confidence = scan.classification.confidence if scan and scan.classification else None
    handled = scan is not None and bool(await _handled_scan_ids(db, scan_id))
    if scan is None or not scan.flagged or _decide(confidence, handled, threshold)[0] != "remove":
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
        handled = await _handled_scan_ids(db)
        report = Report(threshold=threshold, applied=apply,
                        admin=admin.username if admin else None)
        for scan_id, scanned_at, cultivar, ripeness, confidence in rows:
            action, reason = _decide(confidence, scan_id in handled, threshold)
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
            if await _remove_flag(db, decision.scan_id, admin, threshold):
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
            lines.append(
                f"{report.skipped} scan{'' if report.skipped == 1 else 's'} changed while the "
                "command ran and were left as they are."
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
    """The backend's own session factory; honours a running backup or restore."""
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
    print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
