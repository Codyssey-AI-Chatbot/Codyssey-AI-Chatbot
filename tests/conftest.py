"""테스트 공통 설정.

app 을 import 하기 전에 환경 변수를 먼저 지정해야 한다. (환경 변수는 .env 보다 우선하므로
개발자의 로컬 .env 와 app.db 는 테스트에 영향을 주지 않는다.)
B, C 의 테스트도 이 파일의 `client` 픽스처를 그대로 쓸 수 있다.
"""
import os
import tempfile
from pathlib import Path

_TEST_DB_DIR = tempfile.mkdtemp(prefix="chatbot-test-")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEST_DB_DIR, 'test.db').as_posix()}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    """테스트마다 테이블을 새로 만든 깨끗한 DB 와 쿠키가 비어 있는 클라이언트."""
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as test_client:  # 앱 시작 시 create_all 이 실행된다
        yield test_client
