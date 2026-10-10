"""관리자 조회 페이지 테스트 (담당: C): 비활성화, 인증, 전체 로그 조회, 사용자 필터."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr

from app.config import settings
from app.db import SessionLocal
from app.models import ChatLog, User

ADMIN_PASSWORD = "test-admin-password"
ADMIN = ("admin", ADMIN_PASSWORD)
START = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$aGFzaGhhc2hoYXNoaGFzaA"


@pytest.fixture()
def admin_enabled(monkeypatch):
    """테스트 동안만 관리자 비밀번호를 설정한다. (기본값은 미설정 = 페이지 비활성화)"""
    monkeypatch.setattr(settings, "admin_password", SecretStr(ADMIN_PASSWORD))


def add_user_with_logs(username: str, count: int) -> int:
    with SessionLocal() as db:
        user = User(username=username, password_hash=ARGON2_HASH)
        db.add(user)
        db.commit()
        db.add_all(
            [
                ChatLog(
                    user_id=user.id,
                    question=f"{username} 질문 {index}",
                    answer=f"{username} 답변 {index}",
                    created_at=START + timedelta(minutes=index),
                )
                for index in range(1, count + 1)
            ]
        )
        db.commit()
        return user.id


@pytest.mark.parametrize("unset_value", [None, SecretStr("")])
def test_admin_page_is_disabled_without_password(client, monkeypatch, unset_value):
    # 개발자의 .env 에 ADMIN_PASSWORD 가 있어도 영향을 받지 않도록 미설정 상태를 직접 만든다.
    monkeypatch.setattr(settings, "admin_password", unset_value)

    response = client.get("/admin", auth=ADMIN)

    assert response.status_code == 404


def test_admin_page_requires_basic_auth(client, admin_enabled):
    response = client.get("/admin")

    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")


@pytest.mark.parametrize(
    "credentials",
    [("admin", "wrong-password"), ("someone", ADMIN_PASSWORD), ("admin", "")],
)
def test_admin_page_rejects_wrong_credentials(client, admin_enabled, credentials):
    response = client.get("/admin", auth=credentials)

    assert response.status_code == 401


def test_admin_page_is_not_opened_by_a_normal_login(client, admin_enabled):
    account = {"username": "normal_user", "password": "correct-horse"}
    assert client.post("/api/auth/signup", json=account).status_code == 201
    assert client.post("/api/auth/login", json=account).status_code == 200

    response = client.get("/admin")

    assert response.status_code == 401  # 일반 사용자 세션으로는 볼 수 없다


def test_admin_page_lists_all_users_and_logs_without_exposing_hashes(client, admin_enabled):
    add_user_with_logs("alice", 2)
    add_user_with_logs("bob", 1)
    with SessionLocal() as db:
        db.add(User(username="quiet_user", password_hash=ARGON2_HASH))  # 대화가 없는 사용자
        db.commit()

    response = client.get("/admin", auth=ADMIN)

    assert response.status_code == 200
    page = response.text
    assert "사용자 (3명)" in page
    for expected in ("alice 질문 2", "alice 답변 1", "bob 질문 1", "quiet_user"):
        assert expected in page
    assert "2026-03-01 09:02:00" in page  # UTC 00:02 -> KST 09:02
    assert page.index("alice 질문 2") < page.index("alice 질문 1")  # 최신순
    assert "argon2id 해시" in page
    assert ARGON2_HASH not in page and "c2FsdHNhbHQ" not in page  # 해시 원문과 salt 는 노출하지 않는다


def test_admin_page_filters_by_user(client, admin_enabled):
    alice_id = add_user_with_logs("alice", 2)
    add_user_with_logs("bob", 1)

    response = client.get("/admin", params={"user_id": alice_id}, auth=ADMIN)

    assert response.status_code == 200
    assert "alice 질문 1" in response.text and "alice 질문 2" in response.text
    assert "bob 질문 1" not in response.text
    assert "bob" in response.text  # 사용자 목록에는 계속 보인다


def test_admin_page_shows_empty_state(client, admin_enabled):
    response = client.get("/admin", auth=ADMIN)

    assert response.status_code == 200
    assert "아직 가입한 사용자가 없습니다" in response.text
    assert "표시할 대화 로그가 없습니다" in response.text
