"""민감정보를 제외한 채팅·인증 이벤트 로깅."""

import logging

chat_logger = logging.getLogger("app.chat")
chat_logger.setLevel(logging.INFO)
auth_logger = logging.getLogger("app.auth")
auth_logger.setLevel(logging.INFO)


def _ensure_log_handler(logger: logging.Logger = chat_logger) -> None:
    """상위 로깅 설정이 없는 실행 환경에서만 기본 출력기를 추가한다."""

    if logger.hasHandlers():
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)


def log_chat_event(
    event: str,
    *,
    request_id: str,
    user_id: int | None = None,
    path: str | None = None,
    latency_ms: int | None = None,
    chat_id: int | None = None,
    error_type: str | None = None,
) -> None:
    """허용된 추적 필드만 key=value 형식으로 기록한다."""

    fields: list[tuple[str, str | int]] = [("request_id", request_id)]
    if user_id is not None:
        fields.append(("user_id", user_id))
    if path is not None:
        fields.append(("path", path))
    if latency_ms is not None:
        fields.append(("latency_ms", latency_ms))
    if chat_id is not None:
        fields.append(("chat_id", chat_id))
    if error_type is not None:
        fields.append(("error_type", error_type))

    details = " ".join(f"{key}={value}" for key, value in fields)
    _ensure_log_handler()
    chat_logger.info("%s %s", event, details)


def log_auth_event(
    event: str,
    *,
    user_id: int | None = None,
    username: str | None = None,
    reason: str | None = None,
) -> None:
    """인증 이벤트(가입/로그인/로그아웃)를 key=value 형식으로 기록한다.

    비밀번호와 해시는 받지 않는다. username 은 호출하는 쪽에서 형식 검증을 통과한
    값만 넘겨야 한다. (사용자 입력을 그대로 남기면 로그 줄 위조에 쓰일 수 있다.)
    """

    fields: list[tuple[str, str | int]] = []
    if user_id is not None:
        fields.append(("user_id", user_id))
    if username is not None:
        fields.append(("username", username))
    if reason is not None:
        fields.append(("reason", reason))

    details = " ".join(f"{key}={value}" for key, value in fields)
    _ensure_log_handler(auth_logger)
    auth_logger.info("%s %s", event, details)
