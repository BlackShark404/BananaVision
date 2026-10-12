"""Approved provenance eligibility and audited reconciliation, generated data only."""
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Scan
from app.services import dashboard
from tests.test_dashboard import account, db, scan  # noqa: F401
from tests.test_scan_records import mutation, operator_session
from tests.test_time_and_writes import application  # noqa: F401


@pytest.mark.asyncio
async def test_unverified_and_deleted_intake_stock_is_excluded(db):  # noqa: F811 - pytest fixture injection
    owner = account(db)
    valid = scan(db, owner, prediction="1")
    ambiguous = scan(db, owner, prediction="1")
    deleted = scan(db, owner, prediction="1")
    db.session.execute(
        update(Scan).where(Scan.id == ambiguous).values(intake_provenance="unverified")
    )
    db.session.execute(update(Scan).where(Scan.id == deleted).values(
        intake_provenance="linked", intake_origin_id=uuid4()))
    summary = await dashboard.get_summary(db, owner)
    assert summary.expiring_stock_count == 1
    projection = dashboard._scoped_projection(owner, dashboard.now_manila())
    from sqlalchemy import select

    eligible = db.session.scalars(
        select(projection.c.id).where(dashboard._expiring(projection))
    ).all()
    assert eligible == [valid]


def test_admin_reconciles_legacy_stock_without_inventing_links(application):  # noqa: F811 - pytest fixture injection
    app = application
    with Session(app.engine) as db:  # noqa: F811 - pytest fixture injection
        db.execute(update(Scan).where(Scan.id == app.ids.scan).values(
            intake_id=None, intake_origin_id=None, intake_provenance="unverified"))
        db.commit()
    url = f"/api/v1/scans/{app.ids.scan}"
    before = app.client.get(url).json()
    assert before["inventory_eligible"] is False
    body = mutation(
        intake_provenance="unlinked", reason="Verified standalone stock against receiving ledger"
    )
    response = app.client.patch(url + "/provenance", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["intake_id"] is None and result["intake_origin_id"] is None
    assert result["inventory_eligible"] is True and result["revision"] == 2
    assert result["inventory_status"] == before["inventory_status"]
    assert result["is_overridden"] is False
    event = result["history"][-1]
    assert event["kind"] == "provenance" and event["reason"] == body["reason"]
    assert event["previous_values"] == {"intake_provenance": "unverified"}
    assert app.client.patch(url + "/provenance", json=body).json() == result
    assert (
        app.client.patch(
            url + "/provenance", json=mutation(1, intake_provenance="excluded", reason="Stale")
        ).status_code
        == 409
    )
    operator_session(app, app.ids.operator)
    assert (
        app.client.patch(
            url + "/provenance",
            json=mutation(2, intake_provenance="excluded", reason="Unauthorized"),
        ).status_code
        == 403
    )


def test_known_deleted_parent_cannot_be_relabelled_unlinked(application):  # noqa: F811 - pytest fixture injection
    app = application
    with Session(app.engine) as db:  # noqa: F811 - pytest fixture injection
        db.execute(update(Scan).where(Scan.id == app.ids.scan).values(
            intake_id=None, intake_origin_id=uuid4(), intake_provenance="linked"))
        db.commit()
    response = app.client.patch(f"/api/v1/scans/{app.ids.scan}/provenance", json=mutation(
        intake_provenance="unlinked", reason="Cannot erase durable evidence"))
    assert response.status_code == 409
