"""인증된 채팅 API의 입력 검증, AI 호출, 저장 테스트."""

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.ai_client import ChatMessage, get_ai_client
from app.db import SessionLocal
from app.errors import AIServiceError
from app.main import app
from app.models import ChatLog, User

USERNAME = "chat_tester"
PASSWORD = "correct-horse"


class FakeAIClient:
    """네트워크 요청 없이 답변하거나 지정된 오류를 발생시키는 테스트 대역."""

    def __init__(self) -> None:
        self.answer = "가짜 AI 답변"
        self.error: Exception | None = None
        self.calls: list[list[ChatMessage]] = []

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        self.calls.append(list(messages))
        if self.error is not None:
            raise self.error
        return self.answer


@pytest.fixture()
def fake_ai() -> FakeAIClient:
    client = FakeAIClient()
    app.dependency_overrides[get_ai_client] = lambda: client
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def signup_and_login(client) -> int:
    credentials = {"username": USERNAME, "password": PASSWORD}
    assert client.post("/api/auth/signup", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200

    with SessionLocal() as db:
        user_id = db.scalar(select(User.id).where(User.username == USERNAME))
    assert user_id is not None
    return user_id


def load_chat_logs() -> list[ChatLog]:
    with SessionLocal() as db:
        return list(db.scalars(select(ChatLog).order_by(ChatLog.id)))


def create_test_user(username: str) -> int:
    with SessionLocal() as db:
        user = User(username=username, password_hash="unused-test-hash")
        db.add(user)
        db.commit()
        return user.id


def add_chat_history(
    user_id: int,
    count: int,
    *,
    prefix: str,
    start: datetime,
) -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                ChatLog(
                    user_id=user_id,
                    question=f"{prefix} 질문 {index}",
                    answer=f"{prefix} 답변 {index}",
                    created_at=start + timedelta(minutes=index),
                )
                for index in range(1, count + 1)
            ]
        )
        db.commit()


def test_chat_requires_login(client, fake_ai):
    response = client.post("/api/chat", json={"message": "안녕하세요"})

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"
    assert fake_ai.calls == []


def test_chat_rejects_blank_message_before_ai_call(client, fake_ai):
    signup_and_login(client)

    response = client.post("/api/chat", json={"message": " \t\n"})

    assert response.status_code == 400
    assert response.json() == {
        "error": "INVALID_MESSAGE",
        "message": "메시지를 입력해 주세요.",
    }
    assert fake_ai.calls == []
    assert load_chat_logs() == []


def test_chat_accepts_exactly_2000_unicode_characters(client, fake_ai):
    signup_and_login(client)
    message = "가" * 2_000

    response = client.post("/api/chat", json={"message": message})

    assert response.status_code == 200
    assert fake_ai.calls[0] == [ChatMessage(role="user", content=message)]


def test_chat_rejects_more_than_2000_characters_before_ai_call(client, fake_ai):
    signup_and_login(client)

    response = client.post("/api/chat", json={"message": "가" * 2_001})

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_MESSAGE"
    assert fake_ai.calls == []
    assert load_chat_logs() == []


def test_chat_success_returns_answer_and_saves_current_user(client, fake_ai):
    user_id = signup_and_login(client)

    response = client.post("/api/chat", json={"message": "저장할 질문"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == fake_ai.answer
    assert isinstance(body["chat_id"], int)

    logs = load_chat_logs()
    assert len(logs) == 1
    assert logs[0].id == body["chat_id"]
    assert logs[0].user_id == user_id
    assert logs[0].question == "저장할 질문"
    assert logs[0].answer == fake_ai.answer


def test_chat_ai_failure_does_not_save_log(client, fake_ai):
    signup_and_login(client)
    fake_ai.error = AIServiceError("test AI failure")

    with pytest.raises(AIServiceError, match="test AI failure"):
        client.post("/api/chat", json={"message": "실패할 질문"})

    assert len(fake_ai.calls) == 1
    assert load_chat_logs() == []


def test_chat_context_without_history_sends_only_current_question(client, fake_ai):
    signup_and_login(client)

    response = client.post("/api/chat", json={"message": "첫 질문"})

    assert response.status_code == 200
    assert fake_ai.calls == [[ChatMessage(role="user", content="첫 질문")]]


def test_chat_context_uses_recent_five_in_chronological_order(client, fake_ai):
    user_id = signup_and_login(client)
    add_chat_history(
        user_id,
        7,
        prefix="내 대화",
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    response = client.post("/api/chat", json={"message": "현재 질문"})

    assert response.status_code == 200
    assert fake_ai.calls == [
        [
            ChatMessage(role="user", content="내 대화 질문 3"),
            ChatMessage(role="assistant", content="내 대화 답변 3"),
            ChatMessage(role="user", content="내 대화 질문 4"),
            ChatMessage(role="assistant", content="내 대화 답변 4"),
            ChatMessage(role="user", content="내 대화 질문 5"),
            ChatMessage(role="assistant", content="내 대화 답변 5"),
            ChatMessage(role="user", content="내 대화 질문 6"),
            ChatMessage(role="assistant", content="내 대화 답변 6"),
            ChatMessage(role="user", content="내 대화 질문 7"),
            ChatMessage(role="assistant", content="내 대화 답변 7"),
            ChatMessage(role="user", content="현재 질문"),
        ]
    ]
    assert sum(
        message.content == "현재 질문" for message in fake_ai.calls[0]
    ) == 1


def test_chat_context_excludes_other_users_history(client, fake_ai):
    current_user_id = signup_and_login(client)
    other_user_id = create_test_user("other_context_user")
    start = datetime(2026, 2, 1, tzinfo=timezone.utc)
    add_chat_history(current_user_id, 1, prefix="내 대화", start=start)
    add_chat_history(other_user_id, 3, prefix="다른 사용자", start=start)

    response = client.post("/api/chat", json={"message": "격리 확인 질문"})

    assert response.status_code == 200
    assert fake_ai.calls == [
        [
            ChatMessage(role="user", content="내 대화 질문 1"),
            ChatMessage(role="assistant", content="내 대화 답변 1"),
            ChatMessage(role="user", content="격리 확인 질문"),
        ]
    ]
    assert all(
        "다른 사용자" not in message.content for message in fake_ai.calls[0]
    )
