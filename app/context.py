"""사용자별 대화 컨텍스트 조회."""

from sqlalchemy import select
from sqlalchemy.orm import Session

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
