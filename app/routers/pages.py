"""화면 라우터 (담당: C).

Jinja2 템플릿으로 HTML 만 그린다. 데이터 처리와 인증 판단은 모두 A/B 의 JSON API 와
`app.auth` 의존성에 맡기고, 이 모듈은 어떤 템플릿을 어떤 컨텍스트로 보여 줄지만 정한다.
예외는 관리자 페이지(/admin)로, 사용자 계정과 별개인 비밀번호(HTTP Basic)로 보호한다.
"""
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user_or_redirect
from app.config import settings
from app.db import get_db
from app.models import User
from app.routers.logs import as_utc, list_all_chat_logs, list_user_chat_logs, list_users_with_chat_counts

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
KST = timezone(timedelta(hours=9))  # 화면 표시용. 한국은 서머타임이 없어 고정 오프셋으로 충분하다.
HISTORY_PAGE_SIZE = 50  # ponytail: 페이지네이션 없이 최근 50건만. 더 보려면 /api/me/chats 의 offset 을 쓴다.
ADMIN_USERNAME = "admin"
ADMIN_PAGE_SIZE = 100  # ponytail: 최근 100건만. 더 오래된 로그는 사용자 필터로 좁혀서 본다.

templates = Jinja2Templates(directory=TEMPLATES_DIR)
router = APIRouter(include_in_schema=False)  # 화면은 Swagger(/docs) 목록에서 제외
_admin_basic = HTTPBasic(auto_error=False)  # 미인증 응답은 require_admin 에서 직접 만든다


def kst_text(value: datetime) -> str:
    """UTC 로 저장된 시각을 화면용 한국 시각 문자열로 바꾼다."""
    return as_utc(value).astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def require_admin(credentials: HTTPBasicCredentials | None = Depends(_admin_basic)) -> None:
    """관리자 페이지 보호.

    ADMIN_PASSWORD 가 없으면 페이지 자체를 끄고(404), 있으면 HTTP Basic 인증을 요구한다.
    브라우저가 기본 제공하는 인증 창을 쓰므로 로그인 화면과 세션을 따로 만들지 않는다.
    """
    password = settings.admin_password.get_secret_value() if settings.admin_password else ""
    if not password:
        raise HTTPException(status_code=404)

    # ponytail: 시도 횟수 제한 없음. 길고 무작위인 비밀번호(Render 가 생성)에 의존한다.
    # 사용자명과 비밀번호를 모두 상수 시간으로 비교해, 어느 쪽이 틀렸는지 응답 시간으로 드러나지 않게 한다.
    name_ok = credentials is not None and secrets.compare_digest(
        credentials.username.encode(), ADMIN_USERNAME.encode()
    )
    password_ok = credentials is not None and secrets.compare_digest(
        credentials.password.encode(), password.encode()
    )
    if not (name_ok and password_ok):
        raise HTTPException(
            status_code=401,
            detail="관리자 인증이 필요합니다.",
            headers={"WWW-Authenticate": 'Basic realm="admin"'},
        )


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
            "created_at": kst_text(log.created_at),
        }
        for log in list_user_chat_logs(db, user.id, limit=HISTORY_PAGE_SIZE)
    ]
    return templates.TemplateResponse(request, "history.html", {"user": user, "logs": logs})


@router.get("/admin", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
def admin_page(
    request: Request,
    user_id: int | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """관리자 조회 화면: 사용자 목록과 모든 사용자의 최근 대화 로그. ?user_id= 로 한 사용자만 볼 수 있다."""
    users = [
        {
            "id": user.id,
            "username": user.username,
            "created_at": kst_text(user.created_at),
            "chat_count": chat_count,
            # 해시 원문은 보여 주지 않고 방식 이름만 꺼낸다. 예: "$argon2id$v=19$..." -> "argon2id"
            "hash_scheme": user.password_hash.split("$")[1] if user.password_hash.startswith("$") else "알 수 없음",
        }
        for user, chat_count in list_users_with_chat_counts(db)
    ]
    logs = [
        {
            "id": log.id,
            "user_id": log.user_id,
            "username": username,
            "created_at": kst_text(log.created_at),
            "question": log.question,
            "answer": log.answer,
        }
        for log, username in list_all_chat_logs(db, limit=ADMIN_PAGE_SIZE, user_id=user_id)
    ]
    return templates.TemplateResponse(
        request,
        "admin.html",
        {"users": users, "logs": logs, "selected_user_id": user_id, "page_size": ADMIN_PAGE_SIZE},
    )
