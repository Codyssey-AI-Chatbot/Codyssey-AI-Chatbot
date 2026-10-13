import logging

import pytest
from fastapi import Depends
from sqlalchemy import select

from app.auth import get_current_user_or_redirect
from app.db import SessionLocal
from app.main import app
from app.models import User

CREDENTIALS = {"username": "tester", "password": "correct-horse"}


@app.get("/_test/protected-page")
def _protected_page(user: User = Depends(get_current_user_or_redirect)) -> dict[str, str]:
    return {"username": user.username}


def signup(client, **overrides):
    return client.post("/api/auth/signup", json={**CREDENTIALS, **overrides})


def login(client, **overrides):
    return client.post("/api/auth/login", json={**CREDENTIALS, **overrides})


def test_signup_success_does_not_expose_password(client):
    response = signup(client)

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "tester"
    assert "password" not in body and "password_hash" not in body


def test_signup_stores_hashed_password(client):
    signup(client)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "tester"))
    assert user.password_hash != CREDENTIALS["password"]
    assert user.password_hash.startswith("$argon2")


def test_signup_duplicate_username_returns_409(client):
    signup(client)
    response = signup(client)

    assert response.status_code == 409
    assert response.json()["error"] == "USERNAME_TAKEN"


@pytest.mark.parametrize("username", ["ab", "has space", "한글아이디", "a" * 31])
def test_signup_rejects_invalid_username(client, username):
    response = signup(client, username=username)

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_USERNAME"


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_signup_rejects_invalid_password_length(client, password):
    response = signup(client, password=password)

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_PASSWORD"


def test_login_success_then_me(client):
    signup(client)
    response = login(client)

    assert response.status_code == 200
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "tester"


def test_login_failure_does_not_reveal_whether_username_exists(client):
    signup(client)
    wrong_password = login(client, password="wrong-password")
    unknown_user = login(client, username="nobody")

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json()["error"] == "INVALID_CREDENTIALS"


def test_me_requires_login(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


def test_logout_ends_session(client):
    signup(client)
    login(client)
    assert client.post("/api/auth/logout").status_code == 200

    assert client.get("/api/auth/me").status_code == 401


def test_session_of_deleted_user_is_rejected(client):
    signup(client)
    login(client)
    with SessionLocal() as db:
        db.delete(db.scalar(select(User).where(User.username == "tester")))
        db.commit()

    assert client.get("/api/auth/me").status_code == 401


def test_page_dependency_redirects_anonymous_user_to_login(client):
    response = client.get("/_test/protected-page", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_page_dependency_allows_logged_in_user(client):
    signup(client)
    login(client)
    response = client.get("/_test/protected-page", follow_redirects=False)

    assert response.status_code == 200
    assert response.json() == {"username": "tester"}


def auth_events(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == "app.auth"]


def test_auth_events_are_logged_without_secrets(client, caplog):
    caplog.set_level(logging.INFO, logger="app.auth")

    signup(client)
    login(client, password="wrong-password")
    login(client)
    client.post("/api/auth/logout")

    messages = auth_events(caplog)
    assert messages == [
        "signup_success user_id=1 username=tester",
        "login_failed username=tester reason=invalid_credentials",
        "login_success user_id=1",
        "logout user_id=1",
    ]
    joined = " ".join(messages)
    assert CREDENTIALS["password"] not in joined and "wrong-password" not in joined


def test_failed_signup_is_logged_with_reason(client, caplog):
    signup(client)
    caplog.set_level(logging.INFO, logger="app.auth")
    caplog.clear()  # 위의 첫 가입 로그는 검증 대상에서 뺀다

    signup(client)
    signup(client, username="bad name")
    signup(client, username="newuser", password="short")

    assert auth_events(caplog) == [
        "signup_failed username=tester reason=username_taken",
        "signup_failed reason=invalid_username",
        "signup_failed username=newuser reason=invalid_password",
    ]


def test_login_log_does_not_contain_unvalidated_username(client, caplog):
    caplog.set_level(logging.INFO, logger="app.auth")

    login(client, username="fake\nINFO login_success user_id=999")

    messages = auth_events(caplog)
    assert messages == ["login_failed reason=invalid_credentials"]
    assert all("\n" not in message for message in messages)


def test_logout_without_session_logs_no_user(client, caplog):
    caplog.set_level(logging.INFO, logger="app.auth")

    client.post("/api/auth/logout")

    assert auth_events(caplog) == ["logout "]
