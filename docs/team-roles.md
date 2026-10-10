# 팀 역할 분담과 협업 규칙

## 역할 분담

| | A — 인증·DB 기반 | B — AI 챗봇 파이프라인 | C — UI·로그 조회·배포·문서 |
|---|---|---|---|
| 담당자 | @junhnno | @Wattamelon | @ADOHI |
| 요구사항 | 2 (인증/접근 제어), 4의 저장 부분 | 3 (AI 호출·컨텍스트), 5 (로그·예외·검증) | 1 (웹 UI), 4의 조회 부분, 6 (배포), 문서 |
| 소유 파일 | `app/main.py`, `app/config.py`, `app/db.py`, `app/models.py`, `app/auth.py`, `app/routers/auth.py` | `app/ai_client.py`, `app/context.py`, `app/routers/chat.py`, `app/logging_conf.py`, `app/errors.py` | `app/templates/*`, `app/static/*`, `app/routers/pages.py`, `app/routers/logs.py`, `scripts/check_logs.sql`, `README.md`, 배포 설정 |
| 테스트 | `tests/test_auth.py` | `tests/test_chat.py` | `tests/test_logs.py` |

요구사항 번호는 과제 문서 "4. 기능 요구 사항"의 순서를 따른다.

파일 소유를 겹치지 않게 해서 머지 충돌을 줄이고, README의 "개인별 작업 요약"이 Git 이력과 일치하도록 한다.
`app/main.py`에는 모든 라우터가 이미 등록되어 있으므로 B, C는 자신의 `app/routers/*.py`를 채우기만 하면 된다.

## 먼저 합의한 인터페이스

- **A → B, C**: `get_current_user` 의존성. 비로그인 시 401 또는 로그인 페이지로 리다이렉트한다.
- **A → B, C**: `ChatLog(id, user_id, question, answer, created_at)` 모델과 `get_db` 세션.
- **B → C**: `POST /api/chat`
  - 요청: `{"message": "..."}`
  - 성공 응답: `{"answer": "...", "chat_id": 1}`
  - 실패 응답: `{"error": "AI_TIMEOUT", "message": "..."}`

## 브랜치 전략

- `main`: 배포용. `develop`에서 올리는 릴리스 PR로만 머지한다.
- `develop`: 통합 브랜치. 모든 기능 PR의 대상이다.
- `feature/<영역>-<내용>`: 기능 단위 브랜치. 예: `feature/auth-signup`.
- PR은 본인이 아닌 팀원 1명이 승인한 뒤 머지한다. squash 머지는 쓰지 않는다.
- 커밋 메시지는 `feat:`, `fix:`, `docs:`, `test:`, `chore:` 접두어로 통일한다.
- 커밋과 PR은 각자 본인 GitHub 계정으로 올린다.
- `main`, `develop`에는 브랜치 보호(PR 필수, 승인 1명)를 건다.

## PR 순서

| 주차 | A | B | C |
|---|---|---|---|
| 1 | PR1 `feature/project-setup` | PR1 `feature/ai-client` | PR1 `feature/base-ui` |
| 1–2 | PR2 `feature/auth-signup-login` | PR2 `feature/chat-api` | PR2 `feature/chat-ui` |
| 2 | PR3 `feature/access-control` | PR3 `feature/context-strategy` | PR3 `feature/log-view` |
| 3 | PR4 `feature/auth-tests` | PR4 `feature/logging-errors` | PR4 `feature/deploy`, PR5 `docs/readme` |

A의 PR1(프로젝트 뼈대)이 가장 먼저 머지되어야 나머지가 그 위에서 분기할 수 있다.

## 커밋 계획

**A**
1. FastAPI 프로젝트 뼈대와 `requirements.txt`
2. `.env.example`, `.gitignore`, 환경 변수 로딩(`config.py`)
3. SQLite 연결과 세션(`db.py`)
4. `User` 모델
5. `ChatLog` 모델
6. 비밀번호 해싱 유틸
7. 회원가입 API와 입력 검증
8. 로그인 API(세션 쿠키 발급)
9. 로그아웃
10. `get_current_user` 의존성
11. 보호 라우트 적용과 비로그인 리다이렉트
12. 인증 테스트

**B**
1. AI 클라이언트 래퍼(키는 환경 변수에서 로딩)
2. 타임아웃 설정
3. `POST /api/chat` 라우터 기본형
4. 입력 검증(빈 입력, 길이 제한)
5. 응답 DB 저장
6. 최근 N개 대화 컨텍스트 구성
7. 컨텍스트를 AI 호출에 연결
8. 로깅 설정(`request_received`, `ai_call_start`, `ai_call_success`, `ai_call_fail`)
9. `db_save_success`, `db_save_fail` 로그와 `request_id`
10. 타임아웃·실패 예외 처리와 에러 코드 응답
11. AI를 모킹한 성공·타임아웃 테스트
12. 컨텍스트 테스트

**C**
1. 공통 레이아웃 템플릿과 CSS
2. 회원가입 페이지
3. 로그인 페이지
4. 채팅 페이지 마크업
5. 채팅 JS(fetch로 응답을 같은 화면에 표시)
6. 에러 메시지와 로딩 표시
7. `GET /api/me/chats` 내 로그 조회 API
8. 내 대화 기록 화면
9. `scripts/check_logs.sql`
10. 로그 조회 테스트
11. 배포 설정
12. README: 개요, 아키텍처, API 명세, ERD
13. README: 배포 방법, 환경 변수, 팀 역할, DB 확인 가이드
