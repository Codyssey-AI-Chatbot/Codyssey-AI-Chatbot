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


def list_user_chat_logs(
    db: Session, user_id: int, *, limit: int | None, offset: int = 0, before_id: int | None = None
) -> list[ChatLog]:
    """사용자 한 명의 대화 로그를 최신순으로 반환한다. before_id 를 주면 그보다 오래된 로그만.

    limit 이 None 이면 개수 제한 없이 전부 돌려준다.
    """
    statement = select(ChatLog).where(ChatLog.user_id == user_id)
    if before_id is not None:
        # 로그는 현재 시각으로 추가만 되므로 id 가 작을수록 오래된 대화다.
        statement = statement.where(ChatLog.id < before_id)
    statement = statement.order_by(ChatLog.created_at.desc(), ChatLog.id.desc())
    if limit is not None:
        statement = statement.limit(limit).offset(offset)
    return list(db.scalars(statement))


def count_user_chat_logs(db: Session, user_id: int) -> int:
    """사용자 한 명의 전체 대화 수. 화면의 페이지 나누기에 쓴다."""
    return db.scalar(select(func.count()).select_from(ChatLog).where(ChatLog.user_id == user_id)) or 0


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
    before_id: int | None = Query(None, ge=1, description="이 id 보다 오래된 로그만 (이어 불러오기용)"),
    fetch_all: bool = Query(False, alias="all", description="true 면 limit 과 offset 을 무시하고 전부 돌려준다"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChatLog]:
    """내 대화 로그 조회. 다른 사용자의 로그는 user_id 조건으로 조회되지 않는다.

    이어 불러오기는 before_id 를 쓴다. offset 은 조회하는 사이에 새 대화가 생기면 한 칸씩 밀리지만
    before_id 는 밀리지 않는다.
    all=true 는 limit(최대 100)을 건너뛰고 한 번에 전부 돌려준다.
    """
    if fetch_all:
        # ponytail: 전부를 한 번에 메모리에 올린다. 대화가 수만 건인 사용자가 생기면 스트리밍이나 파일 내보내기로 바꾼다.
        return list_user_chat_logs(db, user.id, limit=None, before_id=before_id)
    return list_user_chat_logs(db, user.id, limit=limit, offset=offset, before_id=before_id)
