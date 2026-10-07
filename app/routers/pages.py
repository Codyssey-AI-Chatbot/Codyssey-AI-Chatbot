"""화면 라우터 (담당: C).

Jinja2 템플릿으로 HTML 만 그린다. 데이터 처리와 인증 판단은 모두 A/B 의 JSON API 와
`app.auth` 의존성에 맡기고, 이 모듈은 어떤 템플릿을 어떤 컨텍스트로 보여 줄지만 정한다.
"""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=TEMPLATES_DIR)
router = APIRouter(include_in_schema=False)  # 화면은 Swagger(/docs) 목록에서 제외


@router.get("/")
def index() -> RedirectResponse:
    """첫 화면은 채팅 페이지. 비로그인 상태면 /chat 의 의존성이 /login 으로 보낸다."""
    return RedirectResponse("/chat", status_code=302)
