"""Real PIN routes with isolated stored credentials; no station account inspection."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1 import auth
from app.core.rate_limiter import RateLimiter
from app.core.security import hash_password, hash_pin
from app.models import OperatorProfile, UserAccount
from app.services import runtime_operations
from tests.test_time_and_writes import application  # noqa: F401


@pytest.fixture
def kiosk_pin(application, monkeypatch):  # noqa: F811 - imported pytest fixture
    application.app.include_router(auth.router, prefix='/api/v1')
    monkeypatch.setattr(auth, 'pin_limiter', RateLimiter())
    local = runtime_operations.StationCoordinator()
    monkeypatch.setattr(runtime_operations, 'coordinator', local)
    with Session(application.engine) as db:
        user = db.get(UserAccount, application.ids.operator)
        user.password_hash = hash_password('isolated-account-password')
        profile = db.get(OperatorProfile, application.ids.profile)
        profile.pin_hash = hash_pin('1234')
        profile.requires_pin_change = False
        db.commit()
    with TestClient(runtime_operations.StationAdmissionMiddleware(application.app),
                    raise_server_exceptions=False) as client:
        application.client = client
        yield application, local


def test_stored_1234_pin_authenticates_separately_from_account_password(kiosk_pin):
    app, _ = kiosk_pin
    result = app.client.post('/api/v1/auth/swap', json={'username': 'operator', 'pin': '1234'})
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'success'
    assert result.json()['user']['role'] == 'Operator'
    wrong = app.client.post('/api/v1/auth/swap', json={'username': 'operator', 'pin': '4321'})
    assert wrong.status_code == 200 and wrong.json()['status'] == 'failed'


def test_station_block_does_not_count_as_invalid_pin(kiosk_pin):
    app, local = kiosk_pin
    local.block('recovery-required')
    result = app.client.post('/api/v1/auth/swap', json={'username': 'operator', 'pin': '1234'})
    assert result.status_code == 503
    assert 'recovery-required' in result.json()['detail']
    assert auth.pin_limiter.is_locked('operator') == (False, 0)
