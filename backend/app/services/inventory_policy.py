"""Single stock policy for projections and hydrated scan responses."""
import re

from sqlalchemy import and_, or_

from app.core.time import as_manila

WHITESPACE = " \t\r\n\v\f\u00a0"
NUMBER = r"([0-9]+([.][0-9]+)?|[.][0-9]+)"
PREDICTION_PATTERN = rf"^{NUMBER}([ \t\r\n]*-[ \t\r\n]*{NUMBER})?$"


def eligible_stock(scans):
    return and_(
        scans.c.inventory_status == "In Stock",
        or_(
            and_(scans.c.intake_provenance == "unlinked", scans.c.intake_id.is_(None),
                 scans.c.intake_origin_id.is_(None)),
            and_(scans.c.intake_provenance == "linked",
                 scans.c.intake_origin_id == scans.c.intake_id,
                 scans.c.intake_status == "Active"),
        ),
    )


def inventory_facts(scan, status, now):
    provenance = scan.intake_provenance
    eligible = status == "In Stock" and (
        (provenance == "unlinked" and scan.intake_id is None and scan.intake_origin_id is None)
        or (provenance == "linked" and scan.intake_id is not None
            and scan.intake_origin_id == scan.intake_id
            and scan.intake is not None and scan.intake.status == "Active")
    )
    raw = scan.classification.spoilage_days if scan.classification else None
    remaining = None
    if raw is not None and re.fullmatch(PREDICTION_PATTERN, raw.strip(WHITESPACE)):
        values = [float(value.strip(WHITESPACE)) for value in raw.strip(WHITESPACE).split("-")]
        if len(values) == 1 or values[1] >= values[0]:
            remaining = (
                sum(values) / len(values)
                - (as_manila(now) - as_manila(scan.date_time)).total_seconds() / 86400
            )
    return {"inventory_eligible": bool(eligible), "remaining_days": remaining, "risk_as_of": now}
