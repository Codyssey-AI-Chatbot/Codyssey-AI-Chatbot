"""사용자별 대화 컨텍스트 조회."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_client import ChatMessage
from app.models import ChatLog

DEFAULT_CONTEXT_LIMIT = 5


def get_recent_chat_logs(
    db: Session,
    user_id: int,
    limit: int = DEFAULT_CONTEXT_LIMIT,
) -> list[ChatLog]:
    """사용자의 최근 대화를 AI 전달 순서인 오래된 순서로 반환한다."""

    if limit <= 0:
        return []

    statement = (
        select(ChatLog)
        .where(ChatLog.user_id == user_id)
        .order_by(ChatLog.created_at.desc(), ChatLog.id.desc())
        .limit(limit)
    )
    recent_logs = list(db.scalars(statement))
    recent_logs.reverse()
    return recent_logs


def build_chat_messages(
    chat_logs: Sequence[ChatLog],
    current_message: str,
) -> list[ChatMessage]:
    """과거 Q/A 뒤에 현재 질문을 한 번만 추가해 AI 메시지로 변환한다."""

    messages: list[ChatMessage] = []
    for chat_log in chat_logs:
        messages.extend(
            [
                ChatMessage(role="user", content=chat_log.question),
                ChatMessage(role="assistant", content=chat_log.answer),
            ]
        )
    messages.append(ChatMessage(role="user", content=current_message))
    return messages
