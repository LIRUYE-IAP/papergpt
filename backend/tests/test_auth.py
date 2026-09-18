from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User
from tests.conftest import ApiClient
from tests.helpers import TEST_PASSWORD, auth_headers, login_user, register_user


def test_register_success(client: ApiClient) -> None:
    user = register_user(client, "register@phase1.papergpt.dev", "Ada Lovelace")

    assert user["email"] == "register@phase1.papergpt.dev"
    assert user["name"] == "Ada Lovelace"
    assert "password" not in user
    assert "password_hash" not in user

    with SessionLocal() as db:
        stored_user = db.scalar(
            select(User).where(User.email == "register@phase1.papergpt.dev")
        )
        assert stored_user is not None
        assert stored_user.password_hash != TEST_PASSWORD


def test_duplicate_register_fails(client: ApiClient) -> None:
    register_user(client, "duplicate@phase1.papergpt.dev")
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "DUPLICATE@phase1.papergpt.dev",
            "password": TEST_PASSWORD,
            "name": "Duplicate",
        },
    )

    assert response.status_code == 409


def test_login_success(client: ApiClient) -> None:
    register_user(client, "login@phase1.papergpt.dev")
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login@phase1.papergpt.dev", "password": TEST_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_invalid_login_fails_without_leaking_account_state(client: ApiClient) -> None:
    register_user(client, "invalid-login@phase1.papergpt.dev")
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": "invalid-login@phase1.papergpt.dev", "password": "wrong"},
    )
    unknown_email = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@phase1.papergpt.dev", "password": "wrong"},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_me_requires_authentication(client: ApiClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_me_returns_current_user(client: ApiClient) -> None:
    expected = register_user(client, "me@phase1.papergpt.dev", "Current User")
    token = login_user(client, "me@phase1.papergpt.dev")

    response = client.get("/api/v1/auth/me", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json() == expected
