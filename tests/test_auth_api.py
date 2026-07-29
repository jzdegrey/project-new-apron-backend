from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

VALID_DOB = date.today().replace(year=date.today().year - 25).isoformat()


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _registration_payload(**overrides):
    payload = {
        "username": "janedoe1",
        "password": "sup3rSecret!",
        "confirm_password": "sup3rSecret!",
        "first_name": "Jane",
        "last_name": "Doe",
        "date_of_birth": VALID_DOB,
        "agreed_to_terms": True,
    }
    payload.update(overrides)
    return payload


def _register(client, **overrides):
    return client.post("/api/v1/auth/register", json=_registration_payload(**overrides))


def _login(client, username="janedoe1", password="sup3rSecret!"):
    return client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )


def test_register_creates_user_and_hides_password(client):
    response = _register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "janedoe1"
    assert "password" not in body
    assert "password_hash" not in body


def test_register_rejects_invalid_payload(client):
    response = _register(client, password="short", confirm_password="short")
    assert response.status_code == 422


def test_register_rejects_duplicate_username(client):
    assert _register(client).status_code == 201
    response = _register(client)
    assert response.status_code == 409


def test_register_rejects_duplicate_email(client):
    assert _register(client, email="jane@example.com").status_code == 201
    response = _register(client, username="anotheruser", email="jane@example.com")
    assert response.status_code == 409


def test_login_with_correct_credentials_returns_token(client):
    _register(client)
    response = _login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_with_wrong_password_is_rejected(client):
    _register(client)
    response = _login(client, password="wrong-password")
    assert response.status_code == 401


def test_login_with_unknown_username_is_rejected(client):
    response = _login(client, username="nobody")
    assert response.status_code == 401


def test_me_requires_valid_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_returns_current_user_for_valid_token(client):
    _register(client)
    token = _login(client).json()["access_token"]
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "janedoe1"


def test_account_locks_out_after_exceeding_failed_attempt_threshold(client):
    _register(client)

    # Attempts 1-3 fail but do not lock the account.
    for _ in range(3):
        response = _login(client, password="wrong-password")
        assert response.status_code == 401

    # A correct password still works before the lockout threshold is exceeded.
    assert _login(client).status_code == 200

    # Rack up 4 more failures to cross the threshold again and trigger a lockout.
    for _ in range(3):
        assert _login(client, password="wrong-password").status_code == 401
    fourth_failure = _login(client, password="wrong-password")
    assert fourth_failure.status_code == 401

    # Now locked out: even the correct password is rejected with 423.
    locked_response = _login(client)
    assert locked_response.status_code == 423
    assert "Retry-After" in locked_response.headers
