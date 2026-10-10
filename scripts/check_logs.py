"""check_logs.sql 을 파이썬 표준 sqlite3 로 실행한다. sqlite3 CLI 가 없는 환경(Windows 등)용.

사용법: python scripts/check_logs.py [DB 경로]   (기본값: app.db)
"""
import sqlite3
import sys
from pathlib import Path

SQL_FILE = Path(__file__).with_name("check_logs.sql")


def run_sql_file(db_path: str, sql_path: Path = SQL_FILE) -> list[tuple[list[str], list[tuple]]]:
    """주석을 제외한 SQL 문을 세미콜론 단위로 실행해 (컬럼명 목록, 행 목록) 쌍을 순서대로 돌려준다."""
    lines = sql_path.read_text(encoding="utf-8").splitlines()
    sql = "\n".join(line for line in lines if not line.lstrip().startswith("--"))
    results = []
    with sqlite3.connect(db_path) as conn:
        for statement in filter(None, (part.strip() for part in sql.split(";"))):
            cursor = conn.execute(statement)
            columns = [description[0] for description in cursor.description or []]
            results.append((columns, cursor.fetchall()))
    return results


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "app.db"
    if not Path(db_path).exists():
        sys.exit(f"DB 파일이 없습니다: {db_path}  (서버를 한 번 실행하면 생성됩니다)")
    for columns, rows in run_sql_file(db_path):
        print(" | ".join(columns))
        print("-" * 72)
        for row in rows:
            print(" | ".join(str(value) for value in row))
        print(f"({len(rows)} rows)\n")


if __name__ == "__main__":
    main()
