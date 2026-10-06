"""민감정보를 제외한 채팅 요청 이벤트 로깅."""

import logging

chat_logger = logging.getLogger("app.chat")
chat_logger.setLevel(logging.INFO)


def _ensure_log_handler() -> None:
    """상위 로깅 설정이 없는 실행 환경에서만 기본 출력기를 추가한다."""

    if chat_logger.hasHandlers():
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    chat_logger.addHandler(handler)


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
