"""대화 로그 조회 라우터 (담당: C).

로그인한 사용자가 자신의 대화 로그만 최신순으로 조회한다. 과제의 "사용자 기준 로그 조회/추적"
요구를 API 로 제공하고, 화면(pages.py)도 같은 조회 함수를 사용한다.
관리자 화면(/admin)이 쓰는 전체 사용자 조회 함수도 여기에 둔다. API 로는 노출하지 않는다.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, field_serializer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import ChatLog, User

router = APIRouter(prefix="/api/me", tags=["logs"])

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def as_utc(value: datetime) -> datetime:
    """SQLite 는 시간대를 저장하지 않아 naive 로 읽히므로, 저장 기준인 UTC 를 다시 붙인다."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class ChatLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    answer: str
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> datetime:
        return as_utc(value)


def list_user_chat_logs(db: Session, user_id: int, *, limit: int, offset: int = 0) -> list[ChatLog]:
    """사용자 한 명의 대화 로그를 최신순으로 반환한다."""
    statement = (
        select(ChatLog)
        .where(ChatLog.user_id == user_id)
        .order_by(ChatLog.created_at.desc(), ChatLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(statement))


def list_all_chat_logs(db: Session, *, limit: int, user_id: int | None = None) -> list[tuple[ChatLog, str]]:
    """관리자 화면용. 모든 사용자의 대화 로그를 (로그, 사용자명) 쌍으로 최신순 반환한다. user_id 를 주면 그 사용자만."""
    statement = (
        select(ChatLog, User.username)
        .join(User, User.id == ChatLog.user_id)
        .order_by(ChatLog.created_at.desc(), ChatLog.id.desc())
        .limit(limit)
    )
    if user_id is not None:
        statement = statement.where(ChatLog.user_id == user_id)
    return [(log, username) for log, username in db.execute(statement)]


def list_users_with_chat_counts(db: Session) -> list[tuple[User, int]]:
    """관리자 화면용. 모든 사용자와 각자의 대화 수를 가입 순으로 반환한다. 대화가 없는 사용자도 포함한다."""
    statement = (
        select(User, func.count(ChatLog.id))
        .outerjoin(ChatLog, ChatLog.user_id == User.id)
        .group_by(User.id)
        .order_by(User.id)
    )
    return [(user, count) for user, count in db.execute(statement)]


@router.get("/chats", response_model=list[ChatLogOut])
def my_chats(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="가져올 개수"),
    offset: int = Query(0, ge=0, description="건너뛸 개수 (페이지 이동용)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChatLog]:
    """내 대화 로그 조회. 다른 사용자의 로그는 user_id 조건으로 조회되지 않는다."""
    return list_user_chat_logs(db, user.id, limit=limit, offset=offset)
