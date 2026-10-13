"""인증된 채팅 API 라우터."""

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai_client import AIClient, AICompletion, get_ai_client
from app.auth import get_current_user
from app.context import build_chat_messages, get_recent_chat_logs
from app.db import get_db
from app.errors import (
    AIConfigurationError,
    AIError,
    AIProviderAttempt,
    AIServiceError,
    AITimeoutError,
)
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


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """내부 오류 세부정보를 제외한 일관된 사용자용 응답을 만든다."""

    return JSONResponse(
        status_code=status_code,
        content={"error": code, "message": message},
    )


def log_provider_attempts(
    provider_attempts: tuple[AIProviderAttempt, ...],
    *,
    request_id: str,
    user_id: int,
    call_failed: bool,
) -> None:
    """공급자 시도를 원문 데이터 없이 발생 순서대로 기록한다."""

    for index, provider_attempt in enumerate(provider_attempts):
        log_chat_event(
            "ai_provider_attempt_start",
            request_id=request_id,
            user_id=user_id,
            provider=provider_attempt.provider,
            attempt=provider_attempt.attempt,
        )

        if provider_attempt.succeeded:
            log_chat_event(
                "ai_provider_attempt_success",
                request_id=request_id,
                user_id=user_id,
                provider=provider_attempt.provider,
                attempt=provider_attempt.attempt,
                latency_ms=provider_attempt.latency_ms,
            )
        else:
            failure = provider_attempt.failure
            final_failed_attempt = call_failed and index == len(provider_attempts) - 1
            level = logging.ERROR if final_failed_attempt else logging.WARNING
            log_chat_event(
                "ai_provider_attempt_fail",
                request_id=request_id,
                user_id=user_id,
                provider=provider_attempt.provider,
                attempt=provider_attempt.attempt,
                error_category=failure.category.value if failure else None,
                exception_type=failure.exception_type if failure else None,
                status_code=failure.status_code if failure else None,
                retryable=failure.retryable if failure else None,
                latency_ms=provider_attempt.latency_ms,
                level=level,
            )

        if index + 1 < len(provider_attempts):
            next_attempt = provider_attempts[index + 1]
            log_chat_event(
                "ai_fallback_start",
                request_id=request_id,
                user_id=user_id,
                from_provider=provider_attempt.provider,
                to_provider=next_attempt.provider,
                level=logging.WARNING,
            )


def log_known_ai_failure(
    error: AIError,
    *,
    request_id: str,
    user_id: int,
) -> None:
    """알려진 AI 실패를 원본 예외 메시지와 traceback 없이 기록한다."""

    log_provider_attempts(
        error.attempts,
        request_id=request_id,
        user_id=user_id,
        call_failed=True,
    )
    failure = error.failure
    log_chat_event(
        "ai_call_fail",
        request_id=request_id,
        user_id=user_id,
        provider=failure.provider if failure else None,
        error_category=failure.category.value if failure else None,
        exception_type=(
            failure.exception_type if failure else type(error).__name__
        ),
        status_code=failure.status_code if failure else None,
        retryable=failure.retryable if failure else None,
        fallback_used=len(error.attempts) > 1,
        attempts=len(error.attempts),
        level=logging.ERROR,
    )


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
    except AIConfigurationError as exc:
        log_known_ai_failure(
            exc,
            request_id=request_id,
            user_id=user.id,
        )
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI_NOT_CONFIGURED",
            "현재 AI 서비스를 사용할 수 없습니다. 관리자에게 문의해 주세요.",
        )
    except AITimeoutError as exc:
        log_known_ai_failure(
            exc,
            request_id=request_id,
            user_id=user.id,
        )
        return error_response(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "AI_TIMEOUT",
            "AI 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.",
        )
    except AIServiceError as exc:
        log_known_ai_failure(
            exc,
            request_id=request_id,
            user_id=user.id,
        )
        return error_response(
            status.HTTP_502_BAD_GATEWAY,
            "AI_SERVICE_ERROR",
            "AI 서비스에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        )
    except Exception as exc:
        log_chat_event(
            "ai_call_fail",
            request_id=request_id,
            user_id=user.id,
            exception_type=type(exc).__name__,
            level=logging.ERROR,
            exc_info=True,
        )
        raise
    latency_ms = round((perf_counter() - ai_started_at) * 1_000)
    if isinstance(answer, AICompletion):
        log_provider_attempts(
            answer.attempts,
            request_id=request_id,
            user_id=user.id,
            call_failed=False,
        )
    log_chat_event(
        "ai_call_success",
        request_id=request_id,
        user_id=user.id,
        provider=answer.provider if isinstance(answer, AICompletion) else None,
        latency_ms=latency_ms,
        fallback_used=(
            answer.fallback_used if isinstance(answer, AICompletion) else None
        ),
        attempts=len(answer.attempts) if isinstance(answer, AICompletion) else None,
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
            exception_type=type(exc).__name__,
            level=logging.ERROR,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "DB_SAVE_ERROR",
            "대화를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )
    log_chat_event(
        "db_save_success",
        request_id=request_id,
        user_id=user.id,
        chat_id=chat_id,
    )

    return ChatResponse(answer=answer, chat_id=chat_id)
