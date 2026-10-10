"""로그 조회 테스트 (담당: C): 내 로그 API, 내 대화 기록 화면, 확인용 SQL 스크립트."""
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal, engine
from app.models import ChatLog, User
from scripts.check_logs import run_sql_file

ME = {"username": "log_owner", "password": "correct-horse"}
START = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)


def login(client) -> int:
    assert client.post("/api/auth/signup", json=ME).status_code == 201
    assert client.post("/api/auth/login", json=ME).status_code == 200
    return client.get("/api/auth/me").json()["id"]


def add_logs(user_id: int, count: int, *, prefix: str) -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                ChatLog(
                    user_id=user_id,
                    question=f"{prefix} 질문 {index}",
                    answer=f"{prefix} 답변 {index}",
                    created_at=START + timedelta(minutes=index),
                )
                for index in range(1, count + 1)
            ]
        )
        db.commit()


def add_other_user_with_logs() -> None:
    with SessionLocal() as db:
        other = User(username="other_owner", password_hash="unused-test-hash")
        db.add(other)
        db.commit()
        other_id = other.id
    add_logs(other_id, 2, prefix="남의")


def test_my_chats_requires_login(client):
    response = client.get("/api/me/chats")

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


def test_my_chats_returns_only_own_logs_newest_first(client):
    user_id = login(client)
    add_logs(user_id, 3, prefix="내")
    add_other_user_with_logs()

    response = client.get("/api/me/chats")

    assert response.status_code == 200
    body = response.json()
    assert [item["question"] for item in body] == ["내 질문 3", "내 질문 2", "내 질문 1"]
    assert set(body[0]) == {"id", "question", "answer", "created_at"}
    assert body[0]["created_at"].startswith("2026-03-01T00:03:00")
    assert body[0]["created_at"].endswith(("+00:00", "Z"))  # UTC 임을 명시
    assert all("남의" not in item["question"] for item in body)


def test_my_chats_supports_limit_and_offset(client):
    user_id = login(client)
    add_logs(user_id, 5, prefix="내")

    response = client.get("/api/me/chats", params={"limit": 2, "offset": 1})

    assert response.status_code == 200
    assert [item["question"] for item in response.json()] == ["내 질문 4", "내 질문 3"]


def test_my_chats_rejects_out_of_range_limit(client):
    login(client)

    assert client.get("/api/me/chats", params={"limit": 0}).status_code == 422
    assert client.get("/api/me/chats", params={"limit": 101}).status_code == 422


def test_history_page_redirects_anonymous_user_to_login(client):
    response = client.get("/history", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_history_page_lists_my_logs_in_kst(client):
    user_id = login(client)
    add_logs(user_id, 1, prefix="내")
    add_other_user_with_logs()

    response = client.get("/history")

    assert response.status_code == 200
    assert "내 질문 1" in response.text and "내 답변 1" in response.text
    assert "2026-03-01 09:01:00" in response.text  # UTC 00:01 -> KST 09:01
    assert "남의" not in response.text


def test_history_page_shows_empty_state(client):
    login(client)

    response = client.get("/history")

    assert response.status_code == 200
    assert "아직 대화가 없습니다" in response.text


def test_check_logs_sql_lists_recent_logs_with_username(client):
    user_id = login(client)
    add_logs(user_id, 2, prefix="내")

    recent_logs, per_user = run_sql_file(engine.url.database)

    columns, rows = recent_logs
    assert {"username", "created_at", "question", "answer"} <= set(columns)
    assert rows[0][columns.index("username")] == ME["username"]
    assert rows[0][columns.index("question")] == "내 질문 2"  # 최신순

    columns, rows = per_user
    assert rows[0][columns.index("username")] == ME["username"]
    assert rows[0][columns.index("chat_count")] == 2
