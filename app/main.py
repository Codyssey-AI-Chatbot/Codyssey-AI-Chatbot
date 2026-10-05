"""FastAPI 앱 생성과 라우터 등록.

라우터는 여기서 모두 등록해 두었으므로, B/C 는 이 파일을 수정하지 않고
각자의 app/routers/*.py 안에서 엔드포인트만 추가한다.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401  (테이블 정의를 Base 에 등록하기 위해 import)
from app.db import Base, engine
from app.routers import auth, chat, logs, pages

APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Codyssey AI Chatbot", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(pages.router)
app.include_router(logs.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
