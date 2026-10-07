"""화면 라우터 (담당: C).

Jinja2 템플릿으로 HTML 만 그린다. 데이터 처리와 인증 판단은 모두 A/B 의 JSON API 와
`app.auth` 의존성에 맡기고, 이 모듈은 어떤 템플릿을 어떤 컨텍스트로 보여 줄지만 정한다.
"""
from datetime import timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user_or_redirect
from app.db import get_db
from app.models import User
from app.routers.logs import as_utc, list_user_chat_logs

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
KST = timezone(timedelta(hours=9))  # 화면 표시용. 한국은 서머타임이 없어 고정 오프셋으로 충분하다.
HISTORY_PAGE_SIZE = 50  # ponytail: 페이지네이션 없이 최근 50건만. 더 보려면 /api/me/chats 의 offset 을 쓴다.

templates = Jinja2Templates(directory=TEMPLATES_DIR)
router = APIRouter(include_in_schema=False)  # 화면은 Swagger(/docs) 목록에서 제외


@router.get("/")
def index() -> RedirectResponse:
    """첫 화면은 채팅 페이지. 비로그인 상태면 /chat 의 의존성이 /login 으로 보낸다."""
    return RedirectResponse("/chat", status_code=302)


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "signup.html")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    # 회원가입 직후에는 /login?signup=1 로 들어오므로 완료 안내를 함께 보여 준다.
    return templates.TemplateResponse(
        request, "login.html", {"signed_up": "signup" in request.query_params}
    )


@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, user: User = Depends(get_current_user_or_redirect)) -> HTMLResponse:
    """채팅 화면. 비로그인 사용자는 A 의 의존성이 /login 으로 보낸다."""
    return templates.TemplateResponse(request, "chat.html", {"user": user})


@router.get("/history", response_class=HTMLResponse)
def history_page(
    request: Request,
    user: User = Depends(get_current_user_or_redirect),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """내 대화 기록 화면. API 와 같은 조회 함수를 쓰고, 시각만 KST 문자열로 바꿔 넘긴다."""
    logs = [
        {
            "id": log.id,
            "question": log.question,
            "answer": log.answer,
            "created_at": as_utc(log.created_at).astimezone(KST).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for log in list_user_chat_logs(db, user.id, limit=HISTORY_PAGE_SIZE)
    ]
    return templates.TemplateResponse(request, "history.html", {"user": user, "logs": logs})
