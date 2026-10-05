"""인증 공통 코드: 비밀번호 해싱, 인증 오류, 로그인 사용자 확인 의존성.

다른 라우터에서 로그인 여부를 검사할 때 사용한다.
- API(JSON):  user: User = Depends(get_current_user)              -> 비로그인 시 401 JSON
- 화면(HTML): user: User = Depends(get_current_user_or_redirect)  -> 비로그인 시 /login 으로 리다이렉트
"""
from fastapi import Depends, HTTPException, Request, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

LOGIN_PAGE_PATH = "/login"
SESSION_USER_KEY = "user_id"

_password_hash = PasswordHash.recommended()

# 존재하지 않는 아이디로 로그인할 때도 같은 시간이 걸리도록 검증에 쓰는 더미 해시.
# (응답 시간 차이로 가입된 아이디를 알아내는 것을 막는다.)
DUMMY_PASSWORD_HASH = _password_hash.hash("dummy-password-for-timing")


class AuthError(Exception):
    """인증 관련 오류. main.py 의 핸들러가 {"error": 코드, "message": 문구} JSON 으로 변환한다."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def hash_password(plain: str) -> str:
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _password_hash.verify(plain, hashed)


def _load_session_user(request: Request, db: Session) -> User | None:
    """세션에 저장된 user_id 로 사용자를 찾는다. 없거나 삭제된 사용자면 세션을 비우고 None."""
    user_id = request.session.get(SESSION_USER_KEY)
    if not isinstance(user_id, int):
        return None
    user = db.get(User, user_id)
    if user is None:
        request.session.clear()
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = _load_session_user(request, db)
    if user is None:
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "UNAUTHORIZED", "로그인이 필요합니다.")
    return user


def get_current_user_or_redirect(request: Request, db: Session = Depends(get_db)) -> User:
    user = _load_session_user(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Login required",
            headers={"Location": LOGIN_PAGE_PATH},
        )
    return user
