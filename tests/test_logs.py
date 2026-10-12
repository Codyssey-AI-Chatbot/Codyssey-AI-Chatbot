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


def test_my_chats_before_id_continues_with_older_logs(client):
    user_id = login(client)
    add_logs(user_id, 5, prefix="내")

    first = client.get("/api/me/chats", params={"limit": 2}).json()
    add_logs(user_id, 1, prefix="새")  # 조회하는 사이에 새 대화가 생겨도 이어 불러오기는 밀리지 않는다
    older = client.get("/api/me/chats", params={"limit": 2, "before_id": first[-1]["id"]}).json()

    assert [item["question"] for item in first] == ["내 질문 5", "내 질문 4"]
    assert [item["question"] for item in older] == ["내 질문 3", "내 질문 2"]
    assert client.get("/api/me/chats", params={"before_id": 0}).status_code == 422


def test_my_chats_all_returns_every_own_log_in_one_response(client):
    user_id = login(client)
    add_logs(user_id, 120, prefix="내")  # limit 의 최댓값(100)보다 많다
    add_other_user_with_logs()

    everything = client.get("/api/me/chats", params={"all": "true", "limit": 2, "offset": 5}).json()

    assert len(everything) == 120  # all 이면 limit 과 offset 은 무시한다
    assert everything[0]["question"] == "내 질문 120" and everything[-1]["question"] == "내 질문 1"
    assert all("남의" not in item["question"] for item in everything)
    assert len(client.get("/api/me/chats").json()) == 20  # 기본 동작은 그대로


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
    assert 'class="pager"' not in response.text


def test_history_page_splits_all_logs_into_pages(client):
    user_id = login(client)
    add_logs(user_id, 120, prefix="내")  # 50건씩 3페이지: 120~71, 70~21, 20~1

    first = client.get("/history").text
    last = client.get("/history", params={"page": 3}).text

    assert "전체 120건 중 1~50번째" in first
    assert "<td>내 질문 120</td>" in first and "<td>내 질문 71</td>" in first
    assert "<td>내 질문 70</td>" not in first
    assert 'href="/history?page=2"' in first and "1 / 3 페이지" in first
    assert 'href="/api/me/chats?limit=50&amp;offset=0"' in first
    assert 'href="/api/me/chats?all=true"' in first

    assert "전체 120건 중 101~120번째" in last
    assert "<td>내 질문 20</td>" in last and "<td>내 질문 1</td>" in last
    assert "<td>내 질문 21</td>" not in last
    assert 'href="/history?page=2"' in last and 'href="/history?page=4"' not in last

    # 범위를 벗어난 페이지 번호는 첫 페이지와 마지막 페이지로 맞춘다.
    assert "1 / 3 페이지" in client.get("/history", params={"page": 0}).text
    assert "3 / 3 페이지" in client.get("/history", params={"page": 99}).text


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
