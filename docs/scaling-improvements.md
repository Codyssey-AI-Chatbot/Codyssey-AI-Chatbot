# 동시 접속·장애 대비 개선안

작성 @ADOHI (Claude Code 사용) · 2026-10-12

> **이 문서는 제안입니다. 저장소의 코드는 바꾸지 않았습니다.** 사용자가 한꺼번에 몰릴 때 어디가 먼저 막히는지 분석하고, 어느 파일의 어느 부분을 어떻게 고치면 되는지 적었습니다. 수정안은 저장소 밖의 사본에 적용해서 기존 테스트 57개가 모두 통과하는 것과 아래 실험 결과를 확인했습니다. 코드 링크는 커밋 `7bd5514` 에 고정했습니다.
>
> **실험의 한계**: 로컬 PC 에서 테스트용 클라이언트와 가짜 AI(응답 시간을 고정)로 잰 값입니다. 수정 전후를 비교하기 위한 것이고, Render 에서의 실제 처리량이 아닙니다. 실제 서버를 대상으로 한 부하 테스트는 하지 않았습니다.

## 1. 한눈에 보기

지금 구조는 서버 1대, 프로세스 1개, SQLite 파일 1개입니다. 동시 사용자가 수십 명을 넘으면 아래 순서로 문제가 생깁니다.

| 순서 | 무엇이 문제인가 | 결과 |
|---|---|---|
| 1 | 채팅 요청이 AI 답을 기다리는 동안 DB 연결을 쥐고 있다 | DB 연결 15개가 동시 처리 한도. 넘치면 대기하다가 `500` |
| 2 | 로그인·가입의 비밀번호 해시가 한 번에 메모리 64MB 를 쓴다 | 동시 로그인이 몰리면 메모리가 급증. 인스턴스 한도를 넘으면 서버가 죽는다 |
| 3 | AI 호출 수에 상한이 없다 | 받는 대로 전부 AI API 에 보낸다. 외부 한도를 넘으면 전부 실패한다 |
| 4 | 비동기 함수 안에서 DB 를 일반 호출로 부른다 | 그 호출이 도는 동안 서버 전체가 멈춘다 (평소에는 수 밀리초) |
| 5 | SQLite 기본 저장 방식은 읽기와 쓰기가 서로를 막는다 | 저장이 몰리면 조회가 기다린다 |

개선안은 다섯 가지이고 모두 몇 줄짜리 수정입니다. 구조(FastAPI + SQLite + 서버 1대)는 그대로 둡니다.

| 번호 | 할 일 | 고칠 파일 (담당) | 막아 주는 것 | 실험으로 확인 |
|---|---|---|---|---|
| 1 | 비밀번호 해시를 동시에 4개까지만 실행 | `app/auth.py` (A) | 메모리 급증으로 서버가 죽는 것 | 예 |
| 2 | AI 를 부르기 전에 DB 연결을 반납 | `app/routers/chat.py` (B) | DB 연결 15개 한도 | 예 (5번과 함께) |
| 3 | 동시 AI 호출 수에 상한을 두고, 넘치면 바로 `503` | `app/routers/chat.py` (B) | AI API 한도 초과, 끝없는 대기 | 예 |
| 4 | SQLite 를 WAL 방식으로 전환 | `app/db.py` (A) | 읽기와 쓰기의 충돌 | 테스트 통과만 확인 |
| 5 | 채팅 API 의 DB 호출을 스레드 풀에서 실행 | `app/routers/chat.py` (B) | 서버 전체가 멈추는 순간 | 예 (2번과 함께) |

> **주의: 2번과 5번은 반드시 함께 적용해야 합니다.** 2번만 적용하면 오히려 나빠집니다. 실험에서 동시 30명 요청이 212초 걸렸고 7건이 `500` 으로 실패했습니다. 이유는 [2절](#2-실험-결과)에 있습니다.

## 2. 실험 결과

### 채팅: 동시 요청

가짜 AI 가 정해진 시간 뒤에 답하도록 하고, 로그인한 사용자의 채팅 요청을 한꺼번에 보냈습니다.

| 동시 요청 | AI 응답 시간 | 현재 코드 | 개선안 적용 (3번 상한은 해제) |
|---|---|---|---|
| 30개 | 2초 | 6.8초, 30개 성공 | **2.8초**, 30개 성공 |
| 60개 | 2초 | 15.6초, 60개 성공 | **3.2초**, 60개 성공 |
| 45개 | 16초 | 32.8초, 30개 성공, **15개 `500`** | **16.9초**, 45개 성공 |
| AI 를 기다리는 동안 쓰이는 DB 연결 | | 15개 (한도) | 0개 |

현재 코드에서 45개 중 15개가 실패한 이유는 이렇습니다. 앞의 30개가 연결을 쥐고 AI 를 기다리는 동안, 나머지 15개는 연결이 비기를 30초 기다리다가 포기합니다. 서버 로그에는 `QueuePool limit of size 5 overflow 10 reached, connection timed out` 이 남았습니다.

### 채팅: AI 호출 상한 (개선안 3)

| 동시 요청 | AI 응답 시간 | 개선안 적용 (상한 20) |
|---|---|---|
| 60개 | 2초 | 2.7초. 20개 성공, 40개는 **즉시 `503 AI_BUSY`** |

감당할 만큼만 처리하고 나머지는 기다리게 하지 않고 바로 돌려보냅니다. 채팅 화면은 이미 오류 응답의 안내 문구를 말풍선으로 보여 주므로 화면 코드는 고칠 필요가 없습니다.

### 채팅: 2번만 적용하면 안 되는 이유

| 동시 요청 | AI 응답 시간 | 2번만 적용 (5번 없이) |
|---|---|---|
| 30개 | 2초 | **212.8초**, 23개 성공, 7개 `500` |

2번을 적용하면 저장할 때 DB 연결을 다시 빌려야 합니다. 그런데 5번이 없으면 그 "빌리기"가 이벤트 루프 위에서 일어납니다. 연결이 모자라 기다리게 되면 **서버 전체가 멈춘 채로** 기다립니다. 다른 요청이 연결을 돌려주는 일도 함께 멈추므로, 30초 제한이 끝날 때까지 아무것도 진행되지 않습니다. 5번을 함께 적용하면 기다리는 일이 스레드 풀에서 일어나서 서버는 계속 움직입니다.

### 로그인: 동시 요청과 메모리 (개선안 1)

같은 계정으로 로그인 요청을 한꺼번에 보내고 프로세스의 최대 메모리 사용량을 쟀습니다. 로그인 전에는 139MB 였습니다.

| 동시 로그인 | 현재 코드 | 개선안 1 적용 (동시 4개) |
|---|---|---|
| 8개 | 최대 591MB, 0.4초 | 최대 **334MB**, 0.5초 |
| 32개 | 최대 **1,044MB**, 1.4초 | 최대 **339MB**, 1.5초 |

현재 코드는 동시 요청이 늘수록 메모리가 계속 늘어납니다. 개선안은 요청 수와 상관없이 약 340MB 에서 멈추고, 걸리는 시간은 거의 같습니다.

## 3. 현재 구조와 한계

### 서버 안의 자원 네 가지

| 자원 | 개수 | 하는 일 | 확인 방법 |
|---|---|---|---|
| 프로세스 | 1개 | 서버 프로그램 자체. 죽으면 서비스 전체가 멈춤 | `render.yaml` 의 시작 명령에 `--workers` 가 없음 |
| 이벤트 루프 | 1개 | `async def` 함수를 실행. 여러 요청을 번갈아 처리 | FastAPI 의 동작 방식 |
| 스레드 풀 | 40개 | `def` 함수와 `def` 의존성을 실행 | 로컬에서 값을 읽어 확인 |
| DB 연결 풀 | 5개 + 여유 10개 = 15개, 대기 30초 | DB 를 쓰려면 여기서 연결을 하나 빌려야 함 | 로컬에서 값을 읽어 확인 |

### 채팅 요청 하나가 자원을 쓰는 순서

| 단계 | 하는 일 | 실행되는 곳 | DB 연결 |
|---|---|---|---|
| 1 | 로그인 확인 (사용자 조회) | 스레드 풀 | **빌림** |
| 2 | 최근 대화 5개 조회 | 이벤트 루프 | 쥐고 있음 |
| 3 | AI 답을 기다림 (최대 20초) | 이벤트 루프 (기다리는 동안 양보) | **쥐고 있음** |
| 4 | 대화 저장 | 이벤트 루프 | 쥐고 있음 |
| 5 | 요청 종료 | 스레드 풀 | 반납 |

문제는 3단계입니다. 가장 긴 구간인데 그동안 DB 는 쓰지 않으면서 연결만 붙잡고 있습니다. 2단계와 4단계는 `async def` 함수 안에서 DB 를 일반 호출로 부르기 때문에, 실행되는 동안 이벤트 루프가 다른 요청을 처리하지 못합니다.

### 이미 있는 대비

- AI 호출은 `await` 로 기다리므로 그동안 서버가 다른 요청을 받습니다
- AI 실패, 타임아웃, DB 저장 실패를 모두 잡아 오류 응답으로 바꿉니다. 요청 하나의 실패가 서버를 멈추지 않습니다
- 같은 아이디로 동시에 가입하면 DB 의 중복 금지 규칙이 한쪽을 막고 `409` 로 안내합니다
- Render 는 `/health` 가 60초 동안 계속 실패하면 서버를 다시 시작하고, 배포할 때는 새 서버가 `/health` 를 통과해야 접속을 넘깁니다 (Render 문서 기준)

### 없는 대비

- 예비 서버가 없습니다. 무료 플랜은 인스턴스를 1대보다 늘릴 수 없습니다
- 무료 플랜은 서버가 다시 켜지면 SQLite 파일이 초기화됩니다. 백업이 없습니다
- 요청 횟수 제한이 없습니다
- 서버가 죽었을 때 알려 주는 장치가 없습니다

## 4. 개선안 상세

아래의 "수정안" 코드는 사본에 적용해 테스트와 실험을 통과한 코드를 그대로 옮긴 것입니다. 전체 차이는 [부록](#부록-전체-변경-내용)에 있습니다.

### 개선안 1. 비밀번호 해시의 동시 실행 수 제한

**고칠 곳**: `app/auth.py` (담당 A)

**문제**: 비밀번호 해시(argon2)는 일부러 무겁게 만든 계산이라 한 번에 메모리 64MB 를 씁니다. 로그인과 가입은 스레드 풀에서 실행되어 동시에 최대 40개까지 겹칠 수 있습니다. 수업이 시작되어 수십 명이 한꺼번에 로그인하면 메모리가 급증하고, 인스턴스 한도를 넘으면 운영체제가 서버를 강제로 종료합니다. 다른 문제는 느려지거나 오류가 나는 것이지만 이 문제는 **서버가 죽습니다.**

```python
def hash_password(plain: str) -> str:
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _password_hash.verify(plain, hashed)
```

→ 현재 코드: [`auth.py` L34–L39](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/7bd5514bd6e30fc88035ebfb894f869a69b827b4/app/auth.py#L34-L39)

**수정안**: 동시에 해시를 실행할 수 있는 자리를 4개로 정해 두고, 자리가 날 때까지 줄을 서게 합니다.

```python
# argon2 해시는 한 번에 메모리 64MB 를 쓴다. 동시에 실행할 수를 제한해 메모리 사용량에 상한을 둔다.
# (상한 = 64MB x PASSWORD_HASH_CONCURRENCY. 인스턴스 메모리에 맞춰 조정한다.)
PASSWORD_HASH_CONCURRENCY = 4
_hash_slots = threading.BoundedSemaphore(PASSWORD_HASH_CONCURRENCY)
```

```python
def hash_password(plain: str) -> str:
    with _hash_slots:
        return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    with _hash_slots:
        return _password_hash.verify(plain, hashed)
```

파일 맨 위에 `import threading` 을 추가합니다.

**효과**: 메모리 사용량의 상한이 생깁니다 (64MB × 4). 실험에서 동시 로그인 32개의 최대 메모리가 1,044MB 에서 339MB 로 줄었고, 걸린 시간은 1.4초에서 1.5초로 거의 같았습니다.

**주의**:

- 4라는 값은 인스턴스 메모리에 맞춰 정해야 합니다. 메모리가 512MB 인 인스턴스라면 2~3이 안전합니다
- 줄을 서는 동안 스레드 풀의 스레드를 하나씩 차지합니다. 로그인이 아주 많이 몰리면 다른 화면의 응답도 늦어질 수 있습니다. 그래도 서버가 죽는 것보다는 낫습니다

### 개선안 2. AI 를 부르기 전에 DB 연결 반납

**고칠 곳**: `app/routers/chat.py` (담당 B) · **5번과 반드시 함께 적용**

**문제**: 채팅 요청은 로그인 확인 때 빌린 DB 연결을 AI 답이 올 때까지 쥐고 있습니다. 연결은 15개뿐이라, AI 답을 기다리는 요청이 15개를 넘으면 다음 요청은 연결이 빌 때까지 기다리고, 30초를 넘기면 `500` 으로 실패합니다.

```python
recent_logs = get_recent_chat_logs(db, user.id)
messages = build_chat_messages(recent_logs, payload.message)

ai_started_at = perf_counter()
log_chat_event(
    "ai_call_start",
    request_id=request_id,
    user_id=user.id,
)
try:
    answer = await ai_client.complete(messages)
```

→ 현재 코드: [`routers/chat.py` L77–L87](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/7bd5514bd6e30fc88035ebfb894f869a69b827b4/app/routers/chat.py#L77-L87)

**수정안**: 최근 대화를 읽은 직후 세션을 닫아 연결을 풀에 돌려줍니다. 저장할 때는 세션이 알아서 연결을 다시 빌립니다.

```python
# DB 호출은 기다리는 동안 이벤트 루프를 멈추므로 스레드 풀에서 실행한다.
recent_logs = await run_in_threadpool(get_recent_chat_logs, db, user_id)
messages = build_chat_messages(recent_logs, payload.message)
# AI 답을 기다리는 동안 DB 연결을 쥐고 있지 않도록 여기서 풀에 돌려준다. 저장할 때 다시 빌린다.
await run_in_threadpool(db.close)
```

세션을 닫으면 `user` 객체에서 값을 다시 읽을 수 없으므로, 함수 맨 위에서 사용자 번호를 변수에 꺼내 두고 이후에는 그 변수만 씁니다. 함수 안의 `user.id` 를 모두 `user_id` 로 바꿉니다.

```python
request_id = uuid4().hex
user_id = user.id  # 아래에서 세션을 닫으므로 필요한 값은 먼저 꺼내 둔다
```

**효과**: AI 를 기다리는 동안 쓰이는 DB 연결이 15개에서 0개가 됩니다. 실험에서 동시 45개 요청(AI 16초)이 "30개 성공, 15개 실패"에서 "45개 모두 성공"으로 바뀌었습니다.

**주의**:

- `db.rollback()` 이 아니라 `db.close()` 를 쓴 이유가 있습니다. 기존 테스트 `test_chat_db_failure_rolls_back_and_next_request_succeeds` 가 "저장 실패 때 rollback 이 정확히 1번 불렸는지"를 확인하기 때문에, 여기서 rollback 을 부르면 그 테스트가 깨집니다
- **이 수정만 단독으로 적용하면 안 됩니다.** 저장할 때 연결을 다시 빌리는 일이 이벤트 루프 위에서 일어나게 되어, 연결이 모자라면 서버 전체가 멈춘 채로 기다립니다. 2절의 실험에서 212초가 걸렸습니다

### 개선안 3. 동시 AI 호출 수의 상한

**고칠 곳**: `app/routers/chat.py` (담당 B)

**문제**: 지금은 들어오는 채팅 요청을 전부 AI API 로 보냅니다. 외부 AI API 에는 처리 한도가 있고, 한도를 넘으면 모든 요청이 느려지거나 실패합니다. 받을 수 없는 요청을 붙잡아 두면 사용자는 20초를 기다린 끝에 오류를 봅니다.

**수정안**: 지금 진행 중인 AI 호출 수를 세고, 상한에 닿으면 새 요청을 바로 `503` 으로 돌려보냅니다.

```python
# 동시에 진행할 AI 호출 수의 상한. 넘치는 요청은 기다리게 하지 않고 바로 503 으로 돌려보낸다.
# 이 함수는 이벤트 루프 한 곳에서만 실행되므로 숫자 하나로 세어도 안전하다. (프로세스마다 따로 센다)
AI_MAX_CONCURRENCY = 20
_ai_calls_in_flight = 0
```

```python
if _ai_calls_in_flight >= AI_MAX_CONCURRENCY:
    log_chat_event(
        "ai_call_fail",
        request_id=request_id,
        user_id=user_id,
        error_type="AIBusyError",
    )
    return error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "AI_BUSY",
        "지금 요청이 많습니다. 잠시 후 다시 시도해 주세요.",
    )

ai_started_at = perf_counter()
log_chat_event(
    "ai_call_start",
    request_id=request_id,
    user_id=user_id,
)
_ai_calls_in_flight += 1
try:
    answer = await ai_client.complete(messages)
```

AI 호출이 끝나면 성공이든 실패든 반드시 수를 줄입니다. 기존 `try` 문의 끝에 `finally` 를 붙입니다.

```python
except Exception as exc:
    log_chat_event(
        "ai_call_fail",
        request_id=request_id,
        user_id=user_id,
        error_type=type(exc).__name__,
    )
    raise
finally:
    _ai_calls_in_flight -= 1
```

함수 안에서 전역 변수를 바꾸므로 함수 첫 줄에 `global _ai_calls_in_flight` 를 추가합니다.

**효과**: 실험에서 상한 20일 때 동시 60개 요청 중 20개는 정상 처리되고 40개는 즉시 `503 AI_BUSY` 를 받았습니다. 전체가 2.7초에 끝났습니다.

**주의**:

- 20이라는 값은 임의로 정한 것입니다. AI API 의 실제 한도를 확인해서 정해야 합니다
- 잠금 없이 숫자 하나로 세어도 안전한 이유: 이 함수는 이벤트 루프 한 곳에서만 실행되고, 확인과 증가 사이에 `await` 가 없어서 다른 요청이 끼어들 수 없습니다
- 프로세스를 여러 개 띄우면(`--workers`) 프로세스마다 따로 셉니다. 전체 상한은 "값 × 프로세스 수"가 됩니다
- 적용하면 README 의 오류 코드 표에 `503 AI_BUSY` 를 추가해야 합니다. 화면(`chat.js`)은 고칠 필요가 없습니다. 오류 응답의 안내 문구와 코드를 이미 말풍선으로 보여 줍니다
- 기다리게 하지 않고 바로 거절하는 방식입니다. "5초까지는 기다려 보고 안 되면 거절"로 바꾸려면 `asyncio.Semaphore` 와 `asyncio.wait_for` 를 쓰면 됩니다

### 개선안 4. SQLite 를 WAL 방식으로

**고칠 곳**: `app/db.py` (담당 A), `.gitignore`

**문제**: SQLite 의 기본 저장 방식에서는 누군가 쓰는 동안 다른 사람이 읽지 못하고, 읽는 동안에는 쓰지 못합니다. 우리 서비스는 모든 요청이 로그인 확인을 위해 DB 를 읽으므로, 대화 저장이 몰리면 다른 요청이 줄줄이 기다립니다.

```python
if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        # SQLite 는 외래키를 기본으로 검사하지 않으므로 연결마다 켠다.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
```

→ 현재 코드: [`db.py` L17–L24](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/7bd5514bd6e30fc88035ebfb894f869a69b827b4/app/db.py#L17-L24)

**수정안**: 연결할 때 보내는 설정에 한 줄을 추가합니다. WAL 은 바뀐 내용을 별도 파일에 먼저 적는 방식이라 읽기와 쓰기가 서로를 막지 않습니다.

```python
@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    # SQLite 는 외래키를 기본으로 검사하지 않으므로 연결마다 켠다.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    # WAL: 읽기와 쓰기가 서로를 막지 않는다. (동시에 쓰는 것은 여전히 한 번에 하나)
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
```

**주의**:

- 동시에 쓰는 것은 여전히 한 번에 하나입니다. 읽기와 쓰기의 충돌만 없어집니다
- DB 파일 옆에 `app.db-wal`, `app.db-shm` 파일이 생깁니다. 지금 `.gitignore` 는 `*.db` 만 막고 있어 이 두 파일은 걸러지지 않습니다 ([`.gitignore` L6–L9](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/7bd5514bd6e30fc88035ebfb894f869a69b827b4/.gitignore#L6-L9)). `*.db-wal`, `*.db-shm` 을 추가해야 합니다
- 쓰기가 잠겨 있을 때 기다리는 시간은 파이썬 기본값인 5초가 이미 적용되어 있습니다. 바꾸려면 `create_engine` 의 `connect_args` 에 `"timeout": 초` 를 넣습니다
- 이 개선안은 기존 테스트 통과만 확인했고, 효과를 따로 재는 실험은 하지 않았습니다

### 개선안 5. 채팅 API 의 DB 호출을 스레드 풀에서 실행

**고칠 곳**: `app/routers/chat.py` (담당 B) · **2번과 반드시 함께 적용**

**문제**: 채팅 API 는 `async def` 인데 그 안에서 DB 를 일반 호출로 부릅니다. 그 호출이 실행되는 동안 이벤트 루프는 다른 요청을 처리하지 못합니다. 평소에는 수 밀리초라 드러나지 않지만, DB 가 잠겨 있거나 연결이 모자라 기다리게 되면 그 시간만큼 서버 전체가 멈춥니다. `/health` 응답도 멈추므로 Render 가 서버를 비정상으로 판단할 수 있습니다.

```python
chat_log = ChatLog(user_id=user.id, question=payload.message, answer=answer)
try:
    db.add(chat_log)
    db.commit()
    chat_id = chat_log.id
except Exception as exc:
    log_chat_event(
        "db_save_fail",
        request_id=request_id,
        user_id=user.id,
        error_type=type(exc).__name__,
    )
    try:
        db.rollback()
    except Exception:
        pass
```

→ 현재 코드: [`routers/chat.py` L140–L155](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/7bd5514bd6e30fc88035ebfb894f869a69b827b4/app/routers/chat.py#L140-L155)

**수정안**: DB 를 부르는 세 곳을 `run_in_threadpool` 로 감쌉니다. 저장은 세 줄이 한 묶음이라 작은 함수로 빼냅니다.

```python
def _save_chat_log(db: Session, chat_log: ChatLog) -> int:
    """대화 한 건을 저장하고 새 행의 id 를 돌려준다. 스레드 풀에서 실행한다."""

    db.add(chat_log)
    db.commit()
    return chat_log.id
```

```python
chat_log = ChatLog(user_id=user_id, question=payload.message, answer=answer)
try:
    chat_id = await run_in_threadpool(_save_chat_log, db, chat_log)
except Exception as exc:
    log_chat_event(
        "db_save_fail",
        request_id=request_id,
        user_id=user_id,
        error_type=type(exc).__name__,
    )
    try:
        await run_in_threadpool(db.rollback)
    except Exception:
        pass
```

조회 쪽은 개선안 2의 코드에 이미 포함되어 있습니다 (`await run_in_threadpool(get_recent_chat_logs, db, user_id)`). 파일 위쪽에 import 한 줄을 추가합니다.

```python
from starlette.concurrency import run_in_threadpool
```

**효과**: DB 가 느려지거나 연결을 기다리게 되어도 이벤트 루프는 계속 움직입니다. 2번과 함께 적용했을 때 동시 30개 요청이 6.8초에서 2.8초로, 60개가 15.6초에서 3.2초로 줄었습니다.

**주의**:

- 로그인 확인(`Depends(get_current_user)`)과 DB 세션 준비(`Depends(get_db)`)는 고칠 필요가 없습니다. `def` 로 만든 의존성은 FastAPI 가 원래 스레드 풀에서 실행합니다
- SQLAlchemy 세션은 여러 스레드가 **동시에** 쓰면 안 되지만, 한 요청 안에서 차례대로 쓰는 것은 괜찮습니다. 지금도 세션은 스레드 풀에서 만들어져 이벤트 루프에서 쓰이고 있습니다

## 5. 배포 설정에서 할 수 있는 것

`render.yaml` 은 C 담당입니다. 아래는 코드를 고치지 않고 설정만으로 할 수 있는 일입니다.

```yaml
services:
  - type: web
    name: codyssey-ai-chatbot
    runtime: python
    plan: free
    region: singapore
    branch: main
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
```

→ 현재 코드: [`render.yaml` L14–L23](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/7bd5514bd6e30fc88035ebfb894f869a69b827b4/render.yaml#L14-L23)

| 설정 | 바꾸는 방법 | 효과 | 주의 |
|---|---|---|---|
| 유료 인스턴스 | `plan: free` 를 유료 플랜 값으로 변경 | 잠들지 않음. CPU 와 메모리가 커짐 | 비용이 듭니다. Render 문서에 따르면 무료 인스턴스는 언제든 재시작될 수 있고, 외부로 나가는 요청이 비정상적으로 많으면 정지될 수 있습니다 |
| 디스크 연결 | 서비스에 `disk:` 항목(`name`, `mountPath`, `sizeGB`)을 추가하고 `DATABASE_URL` 을 그 경로로 변경 | 서버가 다시 켜져도 SQLite 파일이 남음 | 유료 플랜이 필요합니다. Render 문서에 따르면 디스크를 붙인 서비스는 여러 대로 늘릴 수 없습니다 |
| 프로세스 수 | 시작 명령에 `--workers 2` 추가 | CPU 코어를 더 씀 | 프로세스마다 메모리를 따로 씁니다. 개선안 1과 3의 상한도 프로세스마다 따로 적용됩니다. CPU 가 작은 인스턴스에서는 효과가 없습니다 |
| 연결 수 상한 | 시작 명령에 `--limit-concurrency 숫자` 추가 | 동시 연결이 숫자를 넘으면 uvicorn 이 바로 `503` 을 돌려줌 | 상한에 닿아 있는 동안에는 Render 의 `/health` 확인도 `503` 을 받게 됩니다. 60초 동안 이어지면 Render 가 서버를 다시 시작하므로 넉넉하게 잡아야 합니다. 개선안 1, 3처럼 앱 안에서 제한하는 쪽이 더 정확합니다 |

## 6. 구조를 바꿔야 넘을 수 있는 한계

위 개선안을 모두 적용해도 남는 한계입니다.

| 한계 | 이유 | 넘으려면 |
|---|---|---|
| 서버 1대가 죽으면 전체 중단 | SQLite 는 서버 안의 파일이라 여러 서버가 함께 쓸 수 없음 | DB 를 PostgreSQL 로 옮긴 뒤 인스턴스를 늘림. `DATABASE_URL` 만 바꾸면 되도록 되어 있음 |
| 동시에 쓰기는 한 번에 하나 | SQLite 의 특성 | PostgreSQL |
| AI API 의 처리 한도 | 우리 서버 밖의 제약 | 요청을 대기열에 넣고 차례대로 처리하거나, 한도가 높은 요금제 사용 |
| 한 사용자가 요청을 계속 보내 자원을 독점 | 사용자별 제한이 없음 | 사용자마다 "진행 중인 요청은 하나"로 제한하거나 분당 횟수 제한 추가 |

## 7. 적용 순서

| 단계 | 할 일 | 이유 |
|---|---|---|
| 0 | 부하 테스트 환경 준비 | 고치기 전후를 같은 방법으로 재야 효과를 알 수 있음 |
| 1 | 개선안 1 (해시 동시 실행 제한) | 서버가 죽는 문제라 가장 먼저. 다른 수정과 독립적 |
| 2 | 개선안 2와 5를 한 PR 로 | 따로 적용하면 안 됨 |
| 3 | 개선안 3 (AI 호출 상한) | AI API 의 실제 한도를 확인한 뒤 값을 정함 |
| 4 | 개선안 4 (WAL) | 효과를 재 본 뒤 결정. `.gitignore` 도 함께 수정 |
| 5 | 필요하면 유료 플랜과 PostgreSQL | 사용자 수가 실제로 늘어날 때 |

부하 테스트는 실제 AI API 를 호출하지 않도록 가짜 AI 서버를 세워 놓고 해야 합니다. 그러지 않으면 테스트만으로 AI 비용이 나가고 외부 한도에 걸립니다. 재야 할 값은 성공률, 응답 시간, 서버의 최대 메모리, 오류 코드별 건수입니다.

각 개선안은 담당자의 파일을 고치는 일이므로, 적용 여부와 값은 담당자(A, B)가 정합니다.

## 부록: 전체 변경 내용

사본에 적용해 테스트 57개 통과와 2절의 실험을 확인한 변경 전체입니다. `-` 는 지우는 줄, `+` 는 추가하는 줄입니다.

### `app/auth.py`

```diff
--- a/app/auth.py
+++ b/app/auth.py
@@ -5,4 +5,6 @@
 - 화면(HTML): user: User = Depends(get_current_user_or_redirect)  -> 비로그인 시 /login 으로 리다이렉트
 """
+import threading
+
 from fastapi import Depends, HTTPException, Request, status
 from pwdlib import PasswordHash
@@ -16,4 +18,9 @@
 
 _password_hash = PasswordHash.recommended()
+
+# argon2 해시는 한 번에 메모리 64MB 를 쓴다. 동시에 실행할 수를 제한해 메모리 사용량에 상한을 둔다.
+# (상한 = 64MB x PASSWORD_HASH_CONCURRENCY. 인스턴스 메모리에 맞춰 조정한다.)
+PASSWORD_HASH_CONCURRENCY = 4
+_hash_slots = threading.BoundedSemaphore(PASSWORD_HASH_CONCURRENCY)
 
 # 존재하지 않는 아이디로 로그인할 때도 같은 시간이 걸리도록 검증에 쓰는 더미 해시.
@@ -33,9 +40,11 @@
 
 def hash_password(plain: str) -> str:
-    return _password_hash.hash(plain)
+    with _hash_slots:
+        return _password_hash.hash(plain)
 
 
 def verify_password(plain: str, hashed: str) -> bool:
-    return _password_hash.verify(plain, hashed)
+    with _hash_slots:
+        return _password_hash.verify(plain, hashed)
 
 
```

### `app/db.py`

```diff
--- a/app/db.py
+++ b/app/db.py
@@ -22,4 +22,6 @@
         cursor = dbapi_connection.cursor()
         cursor.execute("PRAGMA foreign_keys=ON")
+        # WAL: 읽기와 쓰기가 서로를 막지 않는다. (동시에 쓰는 것은 여전히 한 번에 하나)
+        cursor.execute("PRAGMA journal_mode=WAL")
         cursor.close()
 
```

### `app/routers/chat.py`

```diff
--- a/app/routers/chat.py
+++ b/app/routers/chat.py
@@ -8,4 +8,5 @@
 from pydantic import BaseModel
 from sqlalchemy.orm import Session
+from starlette.concurrency import run_in_threadpool
 
 from app.ai_client import AIClient, get_ai_client
@@ -20,4 +21,9 @@
 MAX_MESSAGE_LENGTH = 2_000
 
+# 동시에 진행할 AI 호출 수의 상한. 넘치는 요청은 기다리게 하지 않고 바로 503 으로 돌려보낸다.
+# 이 함수는 이벤트 루프 한 곳에서만 실행되므로 숫자 하나로 세어도 안전하다. (프로세스마다 따로 센다)
+AI_MAX_CONCURRENCY = 20
+_ai_calls_in_flight = 0
+
 
 class ChatRequest(BaseModel):
@@ -41,4 +47,12 @@
         content={"error": code, "message": message},
     )
+
+
+def _save_chat_log(db: Session, chat_log: ChatLog) -> int:
+    """대화 한 건을 저장하고 새 행의 id 를 돌려준다. 스레드 풀에서 실행한다."""
+
+    db.add(chat_log)
+    db.commit()
+    return chat_log.id
 
 
@@ -52,9 +66,12 @@
     """검증된 질문의 AI 답변을 생성하고 성공한 대화만 저장한다."""
 
+    global _ai_calls_in_flight
+
     request_id = uuid4().hex
+    user_id = user.id  # 아래에서 세션을 닫으므로 필요한 값은 먼저 꺼내 둔다
     log_chat_event(
         "request_received",
         request_id=request_id,
-        user_id=user.id,
+        user_id=user_id,
         path="/api/chat",
     )
@@ -75,6 +92,22 @@
         )
 
-    recent_logs = get_recent_chat_logs(db, user.id)
+    # DB 호출은 기다리는 동안 이벤트 루프를 멈추므로 스레드 풀에서 실행한다.
+    recent_logs = await run_in_threadpool(get_recent_chat_logs, db, user_id)
     messages = build_chat_messages(recent_logs, payload.message)
+    # AI 답을 기다리는 동안 DB 연결을 쥐고 있지 않도록 여기서 풀에 돌려준다. 저장할 때 다시 빌린다.
+    await run_in_threadpool(db.close)
+
+    if _ai_calls_in_flight >= AI_MAX_CONCURRENCY:
+        log_chat_event(
+            "ai_call_fail",
+            request_id=request_id,
+            user_id=user_id,
+            error_type="AIBusyError",
+        )
+        return error_response(
+            status.HTTP_503_SERVICE_UNAVAILABLE,
+            "AI_BUSY",
+            "지금 요청이 많습니다. 잠시 후 다시 시도해 주세요.",
+        )
 
     ai_started_at = perf_counter()
@@ -82,6 +115,7 @@
         "ai_call_start",
         request_id=request_id,
-        user_id=user.id,
-    )
+        user_id=user_id,
+    )
+    _ai_calls_in_flight += 1
     try:
         answer = await ai_client.complete(messages)
@@ -90,5 +124,5 @@
             "ai_call_fail",
             request_id=request_id,
-            user_id=user.id,
+            user_id=user_id,
             error_type=type(exc).__name__,
         )
@@ -102,5 +136,5 @@
             "ai_call_fail",
             request_id=request_id,
-            user_id=user.id,
+            user_id=user_id,
             error_type=type(exc).__name__,
         )
@@ -114,5 +148,5 @@
             "ai_call_fail",
             request_id=request_id,
-            user_id=user.id,
+            user_id=user_id,
             error_type=type(exc).__name__,
         )
@@ -126,30 +160,30 @@
             "ai_call_fail",
             request_id=request_id,
-            user_id=user.id,
+            user_id=user_id,
             error_type=type(exc).__name__,
         )
         raise
+    finally:
+        _ai_calls_in_flight -= 1
     latency_ms = round((perf_counter() - ai_started_at) * 1_000)
     log_chat_event(
         "ai_call_success",
         request_id=request_id,
-        user_id=user.id,
+        user_id=user_id,
         latency_ms=latency_ms,
     )
 
-    chat_log = ChatLog(user_id=user.id, question=payload.message, answer=answer)
+    chat_log = ChatLog(user_id=user_id, question=payload.message, answer=answer)
     try:
-        db.add(chat_log)
-        db.commit()
-        chat_id = chat_log.id
+        chat_id = await run_in_threadpool(_save_chat_log, db, chat_log)
     except Exception as exc:
         log_chat_event(
             "db_save_fail",
             request_id=request_id,
-            user_id=user.id,
+            user_id=user_id,
             error_type=type(exc).__name__,
         )
         try:
-            db.rollback()
+            await run_in_threadpool(db.rollback)
         except Exception:
             pass
@@ -162,5 +196,5 @@
         "db_save_success",
         request_id=request_id,
-        user_id=user.id,
+        user_id=user_id,
         chat_id=chat_id,
     )
```
