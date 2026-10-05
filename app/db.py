"""SQLAlchemy 엔진, 세션, Base."""
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    # SQLite 는 기본적으로 생성한 스레드에서만 연결을 쓸 수 있어, FastAPI 환경에서는 해제한다.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        # SQLite 는 외래키를 기본으로 검사하지 않으므로 연결마다 켠다.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """요청 하나당 DB 세션 하나를 열고, 요청이 끝나면 닫는다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
