"""FastAPI 앱 생성과 라우터 등록.

라우터는 여기서 모두 등록해 두었으므로, B/C 는 이 파일을 수정하지 않고
각자의 app/routers/*.py 안에서 엔드포인트만 추가한다.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import models  # noqa: F401  (테이블 정의를 Base 에 등록하기 위해 import)
from app.auth import AuthError
from app.config import settings
from app.db import Base, engine
from app.routers import auth, chat, logs, pages

APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Codyssey AI Chatbot", lifespan=lifespan)

# 로그인 상태는 서명된 세션 쿠키에 user_id 를 담아 유지한다. (HttpOnly, SameSite=Lax)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=settings.session_max_age_seconds,
    same_site="lax",
    https_only=settings.session_cookie_secure,
)

app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


@app.exception_handler(AuthError)
async def auth_error_handler(_request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message})


app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(pages.router)
app.include_router(logs.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
