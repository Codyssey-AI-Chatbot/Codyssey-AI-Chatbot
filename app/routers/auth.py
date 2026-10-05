"""인증 라우터 (담당: A): 회원가입, 로그인, 로그아웃, 내 정보."""
import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    DUMMY_PASSWORD_HASH,
    SESSION_USER_KEY,
    AuthError,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_]{3,30}")
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

INVALID_CREDENTIALS = AuthError(401, "INVALID_CREDENTIALS", "아이디 또는 비밀번호가 올바르지 않습니다.")


class Credentials(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(payload: Credentials, db: Session = Depends(get_db)) -> User:
    if not USERNAME_PATTERN.fullmatch(payload.username):
        raise AuthError(400, "INVALID_USERNAME", "아이디는 영문, 숫자, 밑줄(_)만 사용해 3~30자로 입력해 주세요.")
    if not PASSWORD_MIN_LENGTH <= len(payload.password) <= PASSWORD_MAX_LENGTH:
        raise AuthError(400, "INVALID_PASSWORD", "비밀번호는 8~128자로 입력해 주세요.")
    if db.scalar(select(User).where(User.username == payload.username)) is not None:
        raise AuthError(409, "USERNAME_TAKEN", "이미 사용 중인 아이디입니다.")

    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # 동시에 같은 아이디로 가입한 경우
        db.rollback()
        raise AuthError(409, "USERNAME_TAKEN", "이미 사용 중인 아이디입니다.")
    db.refresh(user)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: Credentials, request: Request, db: Session = Depends(get_db)) -> User:
    # 너무 긴 비밀번호는 해시 검증(CPU 비용)을 하지 않고 바로 실패 처리한다.
    if len(payload.password) > PASSWORD_MAX_LENGTH:
        raise INVALID_CREDENTIALS

    user = db.scalar(select(User).where(User.username == payload.username))
    # 아이디가 없어도 더미 해시로 검증해 응답 시간을 맞추고, 오류 문구도 같게 유지한다.
    password_ok = verify_password(payload.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if user is None or not password_ok:
        raise INVALID_CREDENTIALS

    request.session.clear()  # 이전 세션 내용을 버리고 새로 시작
    request.session[SESSION_USER_KEY] = user.id
    return user


@router.post("/logout")
def logout(request: Request) -> dict[str, str]:
    request.session.clear()
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
