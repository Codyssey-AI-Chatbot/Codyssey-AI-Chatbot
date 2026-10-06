"""인증된 채팅 API 라우터."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai_client import AIClient, get_ai_client
from app.auth import get_current_user
from app.db import get_db
from app.models import User

router = APIRouter()


class ChatRequest(BaseModel):
    """C의 채팅 UI가 전송하는 요청 형식."""

    message: str


class ChatResponse(BaseModel):
    """AI 답변 저장까지 성공했을 때 반환하는 응답 형식."""

    answer: str
    chat_id: int


@router.post("/api/chat", response_model=ChatResponse)
async def create_chat(
    _payload: ChatRequest,
    _user: User = Depends(get_current_user),
    _db: Session = Depends(get_db),
    _ai_client: AIClient = Depends(get_ai_client),
) -> ChatResponse:
    """채팅 처리 의존성을 연결한다. 실제 호출과 저장은 B-06에서 구현한다."""

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Chat processing is not implemented yet",
    )
