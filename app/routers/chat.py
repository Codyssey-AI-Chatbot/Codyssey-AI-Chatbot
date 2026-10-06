"""인증된 채팅 API 라우터."""

from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai_client import AIClient, get_ai_client
from app.auth import get_current_user
from app.context import build_chat_messages, get_recent_chat_logs
from app.db import get_db
from app.logging_conf import log_chat_event
from app.models import ChatLog, User

router = APIRouter()
MAX_MESSAGE_LENGTH = 2_000


class ChatRequest(BaseModel):
    """C의 채팅 UI가 전송하는 요청 형식."""

    message: str


class ChatResponse(BaseModel):
    """AI 답변 저장까지 성공했을 때 반환하는 응답 형식."""

    answer: str
    chat_id: int


@router.post("/api/chat", response_model=ChatResponse)
async def create_chat(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ai_client: AIClient = Depends(get_ai_client),
) -> ChatResponse | JSONResponse:
    """검증된 질문의 AI 답변을 생성하고 성공한 대화만 저장한다."""

    request_id = uuid4().hex
    log_chat_event(
        "request_received",
        request_id=request_id,
        user_id=user.id,
        path="/api/chat",
    )

    if not payload.message.strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "INVALID_MESSAGE", "message": "메시지를 입력해 주세요."},
        )

    if len(payload.message) > MAX_MESSAGE_LENGTH:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "INVALID_MESSAGE",
                "message": f"메시지는 {MAX_MESSAGE_LENGTH:,}자 이하로 입력해 주세요.",
            },
        )

    recent_logs = get_recent_chat_logs(db, user.id)
    messages = build_chat_messages(recent_logs, payload.message)

    ai_started_at = perf_counter()
    log_chat_event(
        "ai_call_start",
        request_id=request_id,
        user_id=user.id,
    )
    try:
        answer = await ai_client.complete(messages)
    except Exception as exc:
        log_chat_event(
            "ai_call_fail",
            request_id=request_id,
            user_id=user.id,
            error_type=type(exc).__name__,
        )
        raise
    latency_ms = round((perf_counter() - ai_started_at) * 1_000)
    log_chat_event(
        "ai_call_success",
        request_id=request_id,
        user_id=user.id,
        latency_ms=latency_ms,
    )

    chat_log = ChatLog(user_id=user.id, question=payload.message, answer=answer)
    try:
        db.add(chat_log)
        db.commit()
        chat_id = chat_log.id
    except Exception as exc:
        log_chat_event(
            "db_save_fail",
            request_id=request_id,
            user_id=user.id,
            error_type=type(exc).__name__,
        )
        raise
    log_chat_event(
        "db_save_success",
        request_id=request_id,
        user_id=user.id,
        chat_id=chat_id,
    )

    return ChatResponse(answer=answer, chat_id=chat_id)
