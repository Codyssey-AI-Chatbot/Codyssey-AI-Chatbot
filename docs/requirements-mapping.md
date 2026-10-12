# 요구사항·제약 사항 대응 설명서

작성 @ADOHI (Claude Code 사용) · 2026-10-12

> 과제 문서의 **4. 기능 요구 사항**과 **6. 제약 사항**을 항목별로 나누어, 어느 코드가 그 항목을 만족하는지 설명하는 문서입니다. 코드 링크는 커밋 `df6226b`(2026-10-12 의 `develop`)에 고정한 주소라, 이후 코드가 바뀌어도 같은 줄이 열립니다. 커밋·PR·테스트 수도 이 커밋 기준이며, 이 문서를 추가한 PR 은 세지 않았습니다. 요구사항 문구는 과제 문서의 내용을 짧게 줄여 옮겼습니다.

## 읽는 법

모든 항목을 같은 순서로 적었습니다.

- **요구**: 과제 문서가 요구하는 것
- **구현**: 어떻게 만족하는지와 핵심 코드. 코드 아래의 `→` 링크를 누르면 GitHub 의 해당 줄이 열립니다
- **확인**: 그 동작을 검증하는 자동 테스트, 또는 직접 확인하는 방법
- **한 문장**: 발표 때 그대로 말할 수 있는 요약

담당 표기는 A = @junhnno (인증·DB), B = @Wattamelon (AI 파이프라인), C = @ADOHI (UI·로그 조회·배포·문서) 입니다.

## 한눈에 보기

| 항목 | 요구 | 핵심 파일 | 담당 |
|---|---|---|---|
| [4-1](#4-1-웹-ui) | 질문 입력 화면, 같은 화면에서 응답 확인 | `templates/chat.html`, `static/chat.js` | C |
| [4-2](#4-2-사용자-인증-및-접근-제어) | 회원가입·로그인, 로그인 여부에 따른 접근 제어 | `auth.py`, `routers/auth.py` | A |
| [4-3](#4-3-ai-챗봇-처리) | 서버에서 AI 호출, 키 노출 방지, 문맥 유지 | `routers/chat.py`, `ai_client.py`, `context.py` | B |
| [4-4](#4-4-대화-로그-저장-및-조회와-추적) | 대화 누적 저장, 추적 필드, 사용자 기준 조회 | `models.py`, `routers/chat.py`, `routers/logs.py` | A·B·C |
| [4-5](#4-5-운영-및-유지보수) | 서버 로그, 예외 처리, 오류 안내, 입력 검증 | `routers/chat.py`, `logging_conf.py` | B |
| [4-6](#4-6-배포-및-접근성) | 외부 접속 가능, 배포·실행 방법 문서화 | `render.yaml`, `README.md` | C |
| [4-7](#4-7-협업-및-형상관리) | 브랜치 전략, PR 머지, 팀원별 커밋 10회 이상 | GitHub 기록, `README.md` | 전원 |
| [6-1](#6-1-민감정보-및-설정-관리) | 민감정보를 코드에 쓰지 않고 환경 변수로 관리 | `config.py`, `.env.example`, `.gitignore` | A·C |
| [6-2](#6-2-운영-안정성) | AI 호출 타임아웃, 처리 단계별 로그 | `ai_client.py`, `routers/chat.py` | B |
| [6-3](#6-3-협업-규칙) | PR 기반 머지, 커밋 10회 이상, 역할 요약 문서 | GitHub 기록, `README.md` | 전원 |

요청 하나가 처리되는 전체 흐름은 [README 2장의 "채팅 요청 처리 흐름"](../README.md#채팅-요청-처리-흐름)에 그림으로 있습니다.

---

## 4. 기능 요구 사항

### 4-1. 웹 UI

담당 C · 관련 PR [#21](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/21), [#22](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/22)

#### (1) 질문을 입력하는 웹 페이지

**요구**: 사용자가 질문을 입력할 수 있는 웹 페이지가 있어야 한다.

**구현**: `/chat` 주소가 채팅 화면을 돌려줍니다. 서버는 Jinja2 템플릿으로 HTML 을 만들고, 그 안에 입력칸과 전송 버튼이 있는 폼이 있습니다.

```python
@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, user: User = Depends(get_current_user_or_redirect)) -> HTMLResponse:
    """채팅 화면. 비로그인 사용자는 A 의 의존성이 /login 으로 보낸다."""
    return templates.TemplateResponse(request, "chat.html", {"user": user})
```

→ [`routers/pages.py` L84–L87](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/pages.py#L84-L87)

```html
<form id="chat-form" class="composer" novalidate>
  <label for="message" class="visually-hidden">메시지</label>
  <textarea id="message" name="message" rows="2" maxlength="2000" required
            placeholder="메시지를 입력하세요 (Enter 전송, Shift+Enter 줄바꿈)"></textarea>
  <button id="send-button" class="button" type="submit">전송</button>
</form>
```

→ [`templates/chat.html` L10–L15](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/templates/chat.html#L10-L15)

**확인**: [`test_chat_page_renders_for_logged_in_user`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_pages.py#L58-L68) 가 로그인한 뒤 `/chat` 응답에 `id="chat-form"` 이 들어 있는지 확인합니다.

> **한 문장**: "`/chat` 라우트가 템플릿으로 입력 폼이 있는 채팅 화면을 그려 줍니다."

#### (2) 같은 화면에서 응답 확인

**요구**: 질문을 입력한 뒤 응답을 같은 화면에서 볼 수 있어야 한다.

**구현**: 폼을 제출해도 페이지가 넘어가지 않게 막고(`event.preventDefault()`), 자바스크립트가 `POST /api/chat` 을 호출합니다. 받은 답변은 말풍선으로 만들어 같은 화면에 덧붙입니다.

```js
form.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) {
    appendError("메시지를 입력해 주세요.", "INVALID_MESSAGE");
    return;
  }
  input.value = "";
  sendMessage(message);
});
```

→ [`static/chat.js` L70–L79](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/static/chat.js#L70-L79)

```js
const data = await response.json().catch(() => null);
loading.remove();

if (response.ok && data?.answer) {
  appendBubble("assistant", data.answer);
} else {
  appendError(
    data?.message ?? "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    data?.error ?? `HTTP_${response.status}`,
  );
}
```

→ [`static/chat.js` L51–L61](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/static/chat.js#L51-L61)

전송부터 화면 갱신까지의 전체 함수는 [`static/chat.js` L33–L68](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/static/chat.js#L33-L68) 입니다. 화면을 다시 열면 최근 대화 20개를 불러와 이어서 보여 줍니다 ([`static/chat.js` L90–L98](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/static/chat.js#L90-L98)).

말풍선에 글을 넣을 때는 `textContent` 를 써서, 사용자가 입력한 태그가 HTML 로 해석되지 않습니다 ([`static/chat.js` L8–L16](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/static/chat.js#L8-L16)).

**확인**: 자바스크립트는 자동 테스트가 없습니다. 브라우저에서 질문을 보내고, 주소가 바뀌지 않은 채 말풍선이 추가되는지 직접 확인합니다.

> **한 문장**: "페이지를 새로 받지 않고 자바스크립트가 채팅 API 를 호출해, 답변을 같은 화면에 말풍선으로 추가합니다."

### 4-2. 사용자 인증 및 접근 제어

담당 A (화면 연동은 C) · 관련 PR [#5](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/5), [#6](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/6), [#21](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/21)

#### (1) 회원가입과 로그인

**요구**: 회원가입과 로그인 기능이 정상 동작해야 한다.

**구현**: 가입할 때 아이디·비밀번호 규칙과 중복을 검사하고, 비밀번호는 **해시로 바꿔서** 저장합니다. 원문은 저장하지 않습니다.

```python
@router.post("/signup", response_model=UserOut, status_code=201)
def signup(payload: Credentials, db: Session = Depends(get_db)) -> User:
    if not USERNAME_PATTERN.fullmatch(payload.username):
        raise AuthError(400, "INVALID_USERNAME", "아이디는 영문, 숫자, 밑줄(_)만 사용해 3~30자로 입력해 주세요.")
    if not PASSWORD_MIN_LENGTH <= len(payload.password) <= PASSWORD_MAX_LENGTH:
        raise AuthError(400, "INVALID_PASSWORD", "비밀번호는 8~128자로 입력해 주세요.")
    if db.scalar(select(User).where(User.username == payload.username)) is not None:
        raise AuthError(409, "USERNAME_TAKEN", "이미 사용 중인 아이디입니다.")

    user = User(username=payload.username, password_hash=hash_password(payload.password))
```

→ [`routers/auth.py` L42–L51](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/auth.py#L42-L51)

로그인은 비밀번호를 검증한 뒤 세션에 `user_id` 를 기록합니다. 아이디가 없는 경우에도 같은 시간 동안 검증하고 같은 문구로 답해서, 가입된 아이디인지 알 수 없게 합니다.

```python
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
```

→ [`routers/auth.py` L62–L76](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/auth.py#L62-L76)

- 해시 함수: [`auth.py` L34–L39](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/auth.py#L34-L39) (pwdlib 권장 설정인 argon2)
- 세션: 서명된 쿠키에 담습니다. 서버의 `SECRET_KEY` 로 서명하므로 사용자가 내용을 고칠 수 없습니다 ([`main.py` L31–L38](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/main.py#L31-L38))
- 로그아웃: 세션을 비웁니다 ([`routers/auth.py` L79–L82](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/auth.py#L79-L82))
- 화면: 폼은 [`templates/signup.html` L7](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/templates/signup.html#L7), [`templates/login.html` L10](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/templates/login.html#L10), 전송 스크립트는 [`static/auth.js` L4–L42](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/static/auth.js#L4-L42)

**확인**: [`test_signup_stores_hashed_password`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_auth.py#L35-L41), [`test_login_success_then_me`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_auth.py#L68-L75), [`test_logout_ends_session`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_auth.py#L95-L100), [`test_login_failure_does_not_reveal_whether_username_exists`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_auth.py#L78-L85)

> **한 문장**: "비밀번호는 argon2 해시로만 저장하고, 로그인하면 서명된 세션 쿠키에 사용자 번호를 담아 로그인 상태를 유지합니다."

#### (2) 로그인 여부에 따른 기능 구분

**요구**: 로그인 상태와 비로그인 상태에서 쓸 수 있는 기능이 구분되어야 한다.

**구현**: A 가 만든 확인 함수 두 개를 라우트에 붙입니다. 로그인하지 않았을 때 API 는 `401` JSON 을, 화면은 `/login` 으로 가라는 `303` 을 돌려줍니다.

```python
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
```

→ [`auth.py` L53–L68](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/auth.py#L53-L68)

| 구분 | 주소 | 비로그인으로 접근하면 |
|---|---|---|
| 누구나 | `/signup`, `/login`, `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`, `/health`, `/static/*`, `/docs` | 그대로 사용 |
| 로그인 필요 (화면) | `/chat`, `/history` | `303` → `/login` |
| 로그인 필요 (API) | `POST /api/chat`, `GET /api/me/chats`, `GET /api/auth/me` | `401 UNAUTHORIZED` |
| 관리자 비밀번호 필요 | `/admin` | `401` (사용자 로그인과 별개인 HTTP Basic). 비밀번호 미설정 서버에서는 `404` |

상단 메뉴도 로그인 여부에 따라 다르게 그립니다 ([`templates/base.html` L12–L22](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/templates/base.html#L12-L22)).

**확인**: [`test_me_requires_login`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_auth.py#L88-L92), [`test_page_dependency_redirects_anonymous_user_to_login`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_auth.py#L113-L117), [`test_chat_page_redirects_anonymous_user_to_login`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_pages.py#L51-L55), [`test_my_chats_requires_login`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_logs.py#L43-L47), [`test_history_page_redirects_anonymous_user_to_login`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_logs.py#L83-L87)

> **한 문장**: "로그인 확인 함수를 라우트의 의존성으로 걸어서, 비로그인 요청은 API 면 401, 화면이면 로그인 페이지로 보냅니다."

#### (3) 챗봇 기능은 로그인한 사용자만

**요구**: 챗봇 질문·응답 기능은 로그인한 사용자만 쓸 수 있어야 한다.

**구현**: 채팅 API 의 매개변수에 `Depends(get_current_user)` 가 있습니다. FastAPI 는 함수 본문보다 의존성을 먼저 실행하므로, 비로그인 요청은 AI 호출까지 가지 못하고 `401` 로 끝납니다.

```python
@router.post("/api/chat", response_model=ChatResponse)
async def create_chat(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    ai_client: AIClient = Depends(get_ai_client),
) -> ChatResponse | JSONResponse:
```

→ [`routers/chat.py` L45–L51](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L45-L51)

채팅 화면 `/chat` 도 같은 방식으로 막혀 있습니다 ([`routers/pages.py` L84–L87](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/pages.py#L84-L87)). 채팅 중에 세션이 만료되면 화면이 `401` 을 보고 로그인 페이지로 이동합니다 ([`static/chat.js` L45–L49](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/static/chat.js#L45-L49)).

**확인**: [`test_chat_requires_login`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L129-L134)

> **한 문장**: "채팅 API 와 채팅 화면 양쪽에 로그인 확인 의존성이 걸려 있어, 로그인하지 않으면 AI 호출 전에 차단됩니다."

### 4-3. AI 챗봇 처리

담당 B · 관련 PR [#8](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/8), [#10](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/10), [#12](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/12)

#### (1) 서버가 질문을 받아 AI API 를 호출

**요구**: 서버가 사용자 질문을 받고, AI API 를 호출해 응답을 만들어야 한다.

**구현**: 채팅 API 가 `{"message": "..."}` 를 받아 문맥을 붙인 뒤 AI 클라이언트를 호출합니다.

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

→ [`routers/chat.py` L77–L87](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L77-L87)

AI 클라이언트는 OpenAI 호환 Chat Completions API 를 부릅니다.

```python
async def complete(self, messages: Sequence[ChatMessage]) -> str:
    try:
        completion = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": message.role, "content": message.content}
                for message in messages
            ],
        )
```

→ [`ai_client.py` L51–L59](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/ai_client.py#L51-L59)

**확인**: [`test_chat_success_returns_answer_and_saves_current_user`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L172-L187). 테스트는 실제 AI 대신 가짜 클라이언트를 끼워 넣어 네트워크 없이 실행됩니다 ([`tests/test_chat.py` L58–L65](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L58-L65)).

> **한 문장**: "채팅 API 가 질문을 받아 최근 대화를 붙이고, 서버에서 OpenAI 호환 API 를 호출해 답변을 받습니다."

#### (2) AI 호출은 서버에서만, 결과만 화면에 반환

**요구**: AI API 호출은 서버에서 수행하고(키 노출 방지), 결과만 화면에 돌려줘야 한다.

**구현**: API 키를 읽고 쓰는 곳은 서버의 이 함수 하나입니다.

```python
api_key = settings.ai_api_key
if api_key is None or not api_key.get_secret_value():
    raise RuntimeError("AI_API_KEY is not configured")

client = AsyncOpenAI(
    api_key=api_key.get_secret_value(),
    base_url=settings.ai_base_url,
    timeout=settings.ai_timeout_seconds,
    max_retries=0,
)
return OpenAIChatClient(client=client, model=settings.ai_model)
```

→ [`ai_client.py` L85–L95](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/ai_client.py#L85-L95)

- 키는 환경 변수에서만 읽고 `SecretStr` 타입으로 보관합니다. 실수로 출력해도 `**********` 로 가려집니다 ([`config.py` L19–L24](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/config.py#L19-L24))
- 브라우저가 아는 주소는 우리 서버의 `/api/chat` 하나입니다 ([`static/chat.js` L39–L43](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/static/chat.js#L39-L43)). AI 서비스의 주소와 키는 브라우저로 내려가지 않습니다
- 응답에 담기는 값은 답변과 저장 번호 둘뿐입니다 ([`routers/chat.py` L29–L33](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L29-L33))
- 서버 로그에도 키, 질문, 답변을 남기지 않습니다. 기록 함수가 정해진 항목만 받습니다 ([`logging_conf.py` L19–L45](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/logging_conf.py#L19-L45))

**확인**: [`test_chat_success_logs_events_without_question_answer_or_key`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L313-L343), [`test_chat_service_failure_returns_502_without_sensitive_logs`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L284-L310). 브라우저 개발자 도구의 Network 탭에서 `/api/chat` 요청과 응답만 보이는 것으로도 확인할 수 있습니다.

> **한 문장**: "API 키는 서버의 환경 변수에만 있고, 브라우저는 우리 서버의 채팅 API 만 호출해 답변 텍스트만 받습니다."

#### (3) 문맥 유지를 위한 컨텍스트 전략

**요구**: 문맥 유지가 가능하도록 최소한의 컨텍스트 구성 전략을 적용해야 한다.

**구현**: 전략은 **"같은 사용자의 최근 대화 5개를 함께 보낸다"** 입니다. DB 에서 최근 5개를 꺼내 오래된 순서로 뒤집습니다.

```python
statement = (
    select(ChatLog)
    .where(ChatLog.user_id == user_id)
    .order_by(ChatLog.created_at.desc(), ChatLog.id.desc())
    .limit(limit)
)
recent_logs = list(db.scalars(statement))
recent_logs.reverse()
return recent_logs
```

→ [`context.py` L24–L32](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/context.py#L24-L32)

과거의 질문과 답변을 번갈아 넣고, 마지막에 지금 질문을 붙여 AI 에 보냅니다.

```python
messages: list[ChatMessage] = []
for chat_log in chat_logs:
    messages.extend(
        [
            ChatMessage(role="user", content=chat_log.question),
            ChatMessage(role="assistant", content=chat_log.answer),
        ]
    )
messages.append(ChatMessage(role="user", content=current_message))
return messages
```

→ [`context.py` L41–L50](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/context.py#L41-L50)

- 사용자 번호로 조회하므로 다른 사용자의 대화는 섞이지 않습니다
- 브라우저가 아니라 DB 에서 꺼내므로, 다시 로그인해도 이어집니다
- 한계: 개수(5개)로만 제한합니다. 대화가 매우 길 때의 글자 수나 토큰 수는 제한하지 않습니다

**확인**: [`test_chat_context_uses_recent_five_in_chronological_order`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L211-L240), [`test_chat_context_excludes_other_users_history`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L243-L262), [`test_chat_context_without_history_sends_only_current_question`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L202-L208)

> **한 문장**: "같은 사용자의 최근 대화 5개를 DB 에서 꺼내 현재 질문 앞에 붙여 보내는 방식으로 문맥을 유지합니다."

### 4-4. 대화 로그 저장 및 조회와 추적

담당: 테이블 A, 저장 B, 조회 C · 관련 PR [#4](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/4), [#10](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/10), [#23](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/23), [#32](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/32)

#### (1) 질문과 응답을 DB 에 누적 저장

**요구**: 사용자 질문과 AI 응답이 DB 에 누적 저장되어야 한다.

**구현**: AI 답변을 받은 직후 질문과 답변을 한 행으로 저장합니다.

```python
chat_log = ChatLog(user_id=user.id, question=payload.message, answer=answer)
try:
    db.add(chat_log)
    db.commit()
    chat_id = chat_log.id
```

→ [`routers/chat.py` L128–L132](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L128-L132)

- 대화 한 번이 새 행 하나입니다. 앱에 로그를 고치거나 지우는 코드가 없어서 기록은 쌓이기만 합니다
- AI 호출이 실패하면 이 줄에 도달하기 전에 오류 응답으로 끝나므로, 실패한 대화는 저장하지 않습니다
- 저장이 실패하면 되돌리고(`rollback`) `500 DB_SAVE_ERROR` 를 돌려줍니다 ([`routers/chat.py` L133–L148](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L133-L148))

**확인**: [`test_chat_success_returns_answer_and_saves_current_user`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L172-L187), [`test_chat_ai_failure_does_not_save_log`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L190-L199), [`test_chat_db_failure_rolls_back_and_next_request_succeeds`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L346-L384)

**주의**: 배포 서버(Render 무료 플랜)는 서버가 잠들거나 다시 배포될 때 디스크가 초기화되어 SQLite 파일이 사라집니다. 배포 서버에서는 서버가 켜져 있는 동안의 기록만 쌓이고, 로컬에서는 계속 쌓입니다. 자세한 내용은 [README 6장](../README.md#6-배포-방법-render)에 있습니다.

> **한 문장**: "AI 답변을 받으면 질문과 답변을 한 행으로 저장하고, 실패한 대화는 저장하지 않습니다."

#### (2) 최소 추적 필드

**요구**: 사용자 식별, 생성 시각, 질문, 응답을 최소한으로 남겨야 한다.

**구현**: `chat_logs` 테이블의 컬럼이 네 항목에 그대로 대응합니다.

```python
class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

→ [`models.py` L23–L30](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/models.py#L23-L30)

| 요구 필드 | 컬럼 | 설명 |
|---|---|---|
| 사용자 식별 | `user_id` | `users.id` 를 가리키는 외래키. 조회가 빠르도록 인덱스를 둠 |
| 생성 시각 | `created_at` | 저장할 때 자동으로 들어가는 UTC 시각 ([`models.py` L10–L11](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/models.py#L10-L11)) |
| 질문 | `question` | 길이 제한 없는 텍스트 |
| 응답 | `answer` | 길이 제한 없는 텍스트 |

시각은 UTC 로 저장하고 화면에 보여 줄 때만 한국 시각으로 바꿉니다 ([`routers/pages.py` L34–L36](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/pages.py#L34-L36)).

> **한 문장**: "`chat_logs` 테이블에 사용자 번호, UTC 생성 시각, 질문, 답변을 저장합니다."

#### (3) 사용자 기준 조회와 추적

**요구**: 사용자 기준으로 로그를 조회하고 추적할 수 있어야 한다.

**구현**: 수단이 네 가지입니다.

| 수단 | 보는 사람 | 쓸 수 있는 곳 | 코드 |
|---|---|---|---|
| 내 로그 API `GET /api/me/chats` | 로그인한 본인 | 로컬, 배포 서버 | [`routers/logs.py` L78–L86](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/logs.py#L78-L86) |
| 내 대화 기록 화면 `/history` | 로그인한 본인 | 로컬, 배포 서버 | [`routers/pages.py` L90–L106](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/pages.py#L90-L106), [`templates/history.html` L14–L32](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/templates/history.html#L14-L32) |
| 관리자 화면 `/admin` (`?user_id=` 로 한 사용자만 보기) | 운영자 | 로컬, 배포 서버 | [`routers/pages.py` L109–L142](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/pages.py#L109-L142), [`routers/logs.py` L54–L75](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/logs.py#L54-L75) |
| 확인용 SQL 과 실행 스크립트 | 운영자 | 로컬만 | [`scripts/check_logs.sql` L11–L32](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/scripts/check_logs.sql#L11-L32), [`scripts/check_logs.py` L12–L22](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/scripts/check_logs.py#L12-L22) |

본인용 API 와 화면은 같은 조회 함수를 씁니다.

```python
def list_user_chat_logs(db: Session, user_id: int, *, limit: int, offset: int = 0) -> list[ChatLog]:
    """사용자 한 명의 대화 로그를 최신순으로 반환한다."""
    statement = (
        select(ChatLog)
        .where(ChatLog.user_id == user_id)
        .order_by(ChatLog.created_at.desc(), ChatLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(statement))
```

→ [`routers/logs.py` L42–L51](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/logs.py#L42-L51)

```python
@router.get("/chats", response_model=list[ChatLogOut])
def my_chats(
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="가져올 개수"),
    offset: int = Query(0, ge=0, description="건너뛸 개수 (페이지 이동용)"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChatLog]:
    """내 대화 로그 조회. 다른 사용자의 로그는 user_id 조건으로 조회되지 않는다."""
    return list_user_chat_logs(db, user.id, limit=limit, offset=offset)
```

→ [`routers/logs.py` L78–L86](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/logs.py#L78-L86)

- 주소에 사용자 번호를 받지 않습니다. 서버가 세션에서 꺼낸 `user.id` 만 조회에 쓰므로 남의 로그를 볼 수 없습니다
- 관리자 화면은 사용자 로그인과 별개인 비밀번호로 보호합니다 ([`routers/pages.py` L39–L62](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/pages.py#L39-L62))
- SQL 스크립트는 서버에 접속해 실행해야 하는데 Render 무료 플랜에는 그 기능이 없어 로컬에서만 씁니다
- 서버 로그의 `user_id` 와 `chat_id` 가 DB 의 행과 이어집니다. 어떤 요청이 어느 행으로 저장됐는지 따라갈 수 있습니다 ([`routers/chat.py` L149–L154](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L149-L154))

**확인**: [`test_my_chats_returns_only_own_logs_newest_first`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_logs.py#L50-L63), [`test_history_page_lists_my_logs_in_kst`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_logs.py#L90-L100), [`test_check_logs_sql_lists_recent_logs_with_username`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_logs.py#L112-L125), [`test_admin_page_filters_by_user`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_admin.py#L100-L109). 실행 예시는 [README 10장](../README.md#10-db-확인-가이드)에 있습니다.

> **한 문장**: "본인은 API 와 대화 기록 화면으로 자기 로그만 보고, 운영자는 관리자 화면과 SQL 스크립트로 사용자별 로그를 확인합니다."

### 4-5. 운영 및 유지보수

담당 B (화면의 오류 표시는 C) · 관련 PR [#14](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/14), [#22](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/22)

#### (1) 서버 로그 이벤트

**요구**: 요청 수신, AI 호출, AI 응답 수신(또는 실패), DB 저장 성공·실패가 서버 로그에 남아야 한다.

**구현**: 채팅 API 가 단계마다 기록 함수를 부릅니다.

| 요구 이벤트 | 로그 이름 | 함께 남는 값 | 코드 |
|---|---|---|---|
| 요청 수신 | `request_received` | 사용자 번호, 경로 | [`routers/chat.py` L54–L60](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L54-L60) |
| AI 호출 | `ai_call_start` | 사용자 번호 | [`routers/chat.py` L80–L85](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L80-L85) |
| AI 응답 수신 | `ai_call_success` | 걸린 시간(ms) | [`routers/chat.py` L120–L126](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L120-L126) |
| AI 실패 | `ai_call_fail` | 오류 종류 | [`routers/chat.py` L88–L94](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L88-L94), [`routers/chat.py` L100–L106](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L100-L106), [`routers/chat.py` L112–L118](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L112-L118) |
| DB 저장 성공 | `db_save_success` | 저장된 행 번호 | [`routers/chat.py` L149–L154](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L149-L154) |
| DB 저장 실패 | `db_save_fail` | 오류 종류 | [`routers/chat.py` L133–L139](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L133-L139) |

```python
request_id = uuid4().hex
log_chat_event(
    "request_received",
    request_id=request_id,
    user_id=user.id,
    path="/api/chat",
)
```

→ [`routers/chat.py` L54–L60](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L54-L60)

요청마다 `request_id` 를 하나 만들어 모든 줄에 붙입니다. 여러 사용자의 로그가 섞여도 한 요청의 흐름을 골라낼 수 있습니다. 기록 함수는 [`logging_conf.py` L19–L45](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/logging_conf.py#L19-L45) 입니다.

성공한 요청 하나가 남기는 로그의 형식입니다.

```text
INFO request_received request_id=3f2a9c1e5b7d4e0f8a6b2c4d9e1f0a7b user_id=1 path=/api/chat
INFO ai_call_start request_id=3f2a9c1e5b7d4e0f8a6b2c4d9e1f0a7b user_id=1
INFO ai_call_success request_id=3f2a9c1e5b7d4e0f8a6b2c4d9e1f0a7b user_id=1 latency_ms=1240
INFO db_save_success request_id=3f2a9c1e5b7d4e0f8a6b2c4d9e1f0a7b user_id=1 chat_id=12
```

**확인**: [`test_chat_success_logs_events_without_question_answer_or_key`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L313-L343), [`test_chat_timeout_returns_504_and_logs_failure`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L265-L281). 로컬은 서버를 켠 터미널에서, 배포 서버는 Render 대시보드의 Logs 탭에서 봅니다.

> **한 문장**: "채팅 요청 하나가 수신, AI 호출, AI 응답, DB 저장 단계마다 같은 요청 번호로 로그를 남깁니다."

#### (2) AI 실패와 타임아웃에도 서비스가 종료되지 않음

**요구**: AI API 가 실패하거나 타임아웃이 나도 서비스가 비정상 종료되지 않아야 한다.

**구현**: 두 단계로 막습니다. 먼저 AI 클라이언트가 외부 라이브러리의 예외를 우리 예외 두 종류로 바꿉니다.

```python
except APITimeoutError as exc:
    raise AITimeoutError("AI service timed out") from exc
except (APIConnectionError, APIStatusError) as exc:
    raise AIServiceError("AI service request failed") from exc
except OpenAIError as exc:
    raise AIServiceError("AI service returned an invalid response") from exc
```

→ [`ai_client.py` L60–L65](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/ai_client.py#L60-L65)

그다음 채팅 API 가 그 예외를 잡아 오류 응답을 정상적으로 돌려줍니다.

```python
try:
    answer = await ai_client.complete(messages)
except AITimeoutError as exc:
    log_chat_event(
        "ai_call_fail",
        request_id=request_id,
        user_id=user.id,
        error_type=type(exc).__name__,
    )
    return error_response(
        status.HTTP_504_GATEWAY_TIMEOUT,
        "AI_TIMEOUT",
        "AI 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.",
    )
```

→ [`routers/chat.py` L86–L99](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L86-L99)

- 예외를 잡아서 응답을 `return` 하므로 요청은 정상적으로 끝나고, 서버는 다음 요청을 계속 받습니다
- AI 가 빈 답변을 준 경우도 오류로 처리합니다 ([`ai_client.py` L67–L73](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/ai_client.py#L67-L73))
- 예상하지 못한 예외는 로그를 남기고 다시 던집니다 ([`routers/chat.py` L112–L119](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L112-L119)). 이때도 FastAPI 가 그 요청만 `500` 으로 처리하고 서버는 계속 동작합니다

**확인**: [`test_chat_timeout_returns_504_and_logs_failure`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L265-L281), [`test_chat_service_failure_returns_502_without_sensitive_logs`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L284-L310), [`test_chat_db_failure_rolls_back_and_next_request_succeeds`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L346-L384)

> **한 문장**: "AI 호출의 예외를 타임아웃과 서비스 오류로 나누어 잡고 오류 응답으로 바꾸므로, 서버는 멈추지 않고 다음 요청을 받습니다."

#### (3) 사용자에게 오류 안내

**요구**: 오류가 났을 때 사용자에게 메시지, 상태 코드 등으로 알려야 한다.

**구현**: 모든 오류 응답은 `{"error": 코드, "message": 안내 문구}` 한 가지 형식입니다. 내부 오류 내용은 응답에 넣지 않습니다.

```python
def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """내부 오류 세부정보를 제외한 일관된 사용자용 응답을 만든다."""

    return JSONResponse(
        status_code=status_code,
        content={"error": code, "message": message},
    )
```

→ [`routers/chat.py` L36–L42](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L36-L42)

| 상황 | 상태 코드 | `error` 값 |
|---|---|---|
| 빈 입력, 2,000자 초과 | `400` | `INVALID_MESSAGE` |
| 로그인하지 않음 | `401` | `UNAUTHORIZED` |
| AI 서비스 오류 | `502` | `AI_SERVICE_ERROR` |
| AI 타임아웃 | `504` | `AI_TIMEOUT` |
| DB 저장 실패 | `500` | `DB_SAVE_ERROR` |

채팅 화면은 이 응답을 받아 오류 말풍선에 안내 문구와 코드를 함께 보여 줍니다. 서버에 아예 닿지 못한 경우도 따로 안내합니다.

```js
  if (response.ok && data?.answer) {
    appendBubble("assistant", data.answer);
  } else {
    appendError(
      data?.message ?? "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
      data?.error ?? `HTTP_${response.status}`,
    );
  }
} catch {
  loading.remove();
  appendError("서버에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.", "NETWORK_ERROR");
```

→ [`static/chat.js` L54–L64](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/static/chat.js#L54-L64)

인증 오류도 같은 형식으로 바꿔 돌려주고 ([`main.py` L43–L45](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/main.py#L43-L45)), 회원가입·로그인 화면이 그 문구를 폼 아래에 보여 줍니다 ([`static/auth.js` L34–L37](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/static/auth.js#L34-L37)).

**확인**: [`test_chat_timeout_returns_504_and_logs_failure`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L265-L281), [`test_chat_rejects_blank_message_before_ai_call`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L137-L148). 화면 표시는 브라우저에서 직접 확인합니다.

> **한 문장**: "오류는 상태 코드와 함께 에러 코드·안내 문구를 JSON 으로 돌려주고, 채팅 화면이 오류 말풍선으로 보여 줍니다."

#### (4) 입력 검증

**요구**: 사용자 입력 검증 로직이 최소 1개 이상 있어야 한다.

**구현**: 채팅 메시지는 서버에서 두 가지를 검사합니다. 공백만 있는 입력과 2,000자를 넘는 입력을 AI 호출 전에 거부합니다.

```python
if not payload.message.strip():
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "INVALID_MESSAGE", "message": "메시지를 입력해 주세요."},
    )

if len(payload.message) > MAX_MESSAGE_LENGTH:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "INVALID_MESSAGE",
            "message": f"메시지는 {MAX_MESSAGE_LENGTH:,}자 이하로 입력해 주세요.",
        },
    )
```

→ [`routers/chat.py` L62–L75](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L62-L75)

| 대상 | 규칙 | 코드 |
|---|---|---|
| 채팅 메시지 | 공백만 있으면 거부, 2,000자 초과 거부 | [`routers/chat.py` L62–L75](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L62-L75) |
| 아이디, 비밀번호 | 영문·숫자·밑줄 3~30자, 8~128자 | [`routers/auth.py` L44–L47](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/auth.py#L44-L47) |
| 로그 조회 `limit`, `offset` | 1~100, 0 이상 | [`routers/logs.py` L80–L81](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/logs.py#L80-L81) |
| 화면 (보조) | 입력칸 `maxlength="2000"`, 빈 입력 차단 | [`templates/chat.html` L12–L13](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/templates/chat.html#L12-L13), [`static/chat.js` L72–L76](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/static/chat.js#L72-L76) |

화면의 검사는 편의를 위한 것이고, 실제 검증은 서버가 합니다. 브라우저를 거치지 않고 API 를 직접 호출할 수 있기 때문입니다.

**확인**: [`test_chat_rejects_blank_message_before_ai_call`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L137-L148), [`test_chat_rejects_more_than_2000_characters_before_ai_call`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L161-L169), [`test_chat_accepts_exactly_2000_unicode_characters`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L151-L158), [`test_signup_rejects_invalid_username`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_auth.py#L53-L57), [`test_my_chats_rejects_out_of_range_limit`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_logs.py#L76-L80)

> **한 문장**: "채팅 메시지는 서버에서 빈 입력과 2,000자 초과를 AI 호출 전에 거부하고, 아이디·비밀번호와 조회 범위도 서버에서 검사합니다."

### 4-6. 배포 및 접근성

담당 C · 관련 PR [#24](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/24), [#30](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/30), [#34](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/34)

#### (1) 외부 네트워크에서 접속 가능

**요구**: 배포된 서비스는 평가 시점에 외부 네트워크에서 접속할 수 있어야 한다.

**구현**: Render 에 배포했습니다. 주소는 https://codyssey-ai-chatbot.onrender.com 입니다. 2026-10-12 에 `/health` 가 `200` 으로 응답하는 것을 확인했습니다 (잠든 상태에서 깨어나는 데 약 45초).

배포 설정은 저장소의 `render.yaml` 에 있습니다.

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

→ [`render.yaml` L14–L23](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/render.yaml#L14-L23)

- `--host 0.0.0.0` 은 바깥에서 오는 접속을 받겠다는 뜻이고, 포트는 Render 가 정해 줍니다(`$PORT`)
- Render 는 `/health` 가 정상 응답해야 배포 성공으로 처리합니다 ([`main.py` L54–L56](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/main.py#L54-L56))
- 배포되는 브랜치는 `main` 입니다. 현재 배포된 커밋은 `5b5751c` 이고, 이 문서의 기준인 `develop` 은 그 뒤에 문서 추가와 로그아웃 스크립트 파일 분리(동작은 같음)만 앞서 있습니다

**주의**: 무료 플랜이라 15분 동안 쓰지 않으면 서버가 잠듭니다. 깨어나는 첫 접속은 1분 가까이 걸리고, 그때 DB 도 초기화됩니다. 시연은 접속한 뒤 가입부터 조회까지 이어서 합니다.

> **한 문장**: "Render 에 배포해 공개 주소로 접속할 수 있고, 배포 설정은 `render.yaml` 에 코드로 남겼습니다."

#### (2) 배포·실행 방법과 환경 변수 설정 방법 문서화

**요구**: 배포·실행 방법과 환경 변수 설정 방법이 문서에 있어야 한다.

**구현**:

| 내용 | 위치 |
|---|---|
| 로컬 실행 방법 | [README 5장](../README.md#5-실행-방법-로컬) |
| Render 배포와 재배포 방법 | [README 6장](../README.md#6-배포-방법-render) |
| 환경 변수 9개의 이름, 필수 여부, 기본값, 설명 | [README 7장](../README.md#7-환경-변수) |
| 복사해서 쓰는 환경 변수 예시 파일 | [`.env.example` L1–L27](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/.env.example#L1-L27) |
| 배포 서버의 환경 변수 설정 | [`render.yaml` L24–L42](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/render.yaml#L24-L42) |

> **한 문장**: "README 에 로컬 실행, Render 배포, 환경 변수 표를 적었고, 예시 파일 `.env.example` 을 함께 제공합니다."

### 4-7. 협업 및 형상관리

담당 전원. 기록은 GitHub 저장소에 있습니다.

#### (1) 브랜치 전략

**요구**: `main` 과 `develop` 을 나누는 등의 브랜치 전략을 적용해야 한다.

**구현**:

| 브랜치 | 역할 |
|---|---|
| `main` | 배포용. `develop` 에서 올리는 릴리스 PR 로만 바뀜 |
| `develop` | 통합용. 모든 기능 PR 의 대상 |
| `feature/*`, `fix/*`, `docs/*`, `chore/*` | 기능 하나를 작업하는 브랜치 |

규칙은 [README 12장](../README.md#12-협업-규칙)과 [`docs/team-roles.md` L26–L34](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/docs/team-roles.md#L26-L34) 에 적혀 있습니다. `develop` 을 `main` 으로 올린 릴리스 PR 은 [#27](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/27), [#29](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/29), [#33](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/33), [#35](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/35) 입니다.

> **한 문장**: "`main` 은 배포, `develop` 은 통합, 기능 브랜치는 작업용으로 나누고 `main` 은 릴리스 PR 로만 올렸습니다."

#### (2) 기능 단위 작업 브랜치

**요구**: 기능 단위 작업 브랜치의 흔적이 있어야 한다.

**구현**: 기능 PR 18개가 각각 별도 브랜치에서 올라왔습니다.

| 담당 | 브랜치 (PR) |
|---|---|
| A | `feature/project-setup` ([#4](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/4)), `feature/auth-signup-login` ([#5](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/5)), `feature/auth-tests` ([#6](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/6)) |
| B | `feature/ai-client` ([#8](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/8)), `feature/chat-api` ([#10](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/10)), `feature/context-strategy` ([#12](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/12)), `feature/logging-errors` ([#14](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/14)) |
| C | `feature/base-ui` ([#21](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/21)), `feature/chat-ui` ([#22](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/22)), `feature/log-view` ([#23](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/23)), `feature/deploy` ([#24](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/24)), `docs/readme` ([#25](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/25)), `fix/render-health-timeout` ([#28](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/28)), `docs/deploy-url` ([#30](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/30)), `feature/admin-log-view` ([#32](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/32)), `fix/render-manual-deploy` ([#34](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/34)), `docs/qna-and-walkthrough` ([#36](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/36)), `chore/logout-script-static` ([#37](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pull/37)) |

브랜치 목록: https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/branches/all

> **한 문장**: "기능마다 브랜치를 만들어 작업했고, 18개 기능 PR 의 브랜치가 저장소에 남아 있습니다."

#### (3) PR 기반 머지 기록

**요구**: PR 을 통해 머지한 기록이 있어야 한다.

**구현**: 머지된 PR 은 22개입니다. 기능 PR 18개는 `develop` 으로, 릴리스 PR 4개는 `main` 으로 들어갔습니다. squash 를 쓰지 않고 머지 커밋을 남겨 개별 커밋 이력이 보존됩니다.

- 머지된 PR 목록: https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/pulls?q=is%3Apr+is%3Amerged
- PR 은 공통 템플릿으로 작성했습니다 ([`.github/pull_request_template.md` L1–L18](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/.github/pull_request_template.md#L1-L18))
- 기능 이슈를 만들고 PR 에서 `Closes #번호` 로 연결했습니다

**알아 둘 점**: 규칙은 "본인이 아닌 팀원 1명이 승인한 뒤 머지"였지만, GitHub 의 승인(Approve) 기능을 쓰지 않아 **승인 기록이 남은 PR 은 없습니다.** C 의 PR 중 팀원이 리뷰하기 어려웠던 것은 PR 본문의 "머지 메모"에 사유를 적고 머지했습니다.

> **한 문장**: "모든 변경은 PR 로 머지했고 22개의 머지 기록이 남아 있습니다. 다만 GitHub 승인 기록은 남기지 못했습니다."

#### (4) 팀원별 커밋 10회 이상

**요구**: 팀원마다 의미 있는 커밋이 10회 이상 있어야 한다.

**구현**: `develop` 기준, 머지 커밋을 뺀 수입니다. 저장소를 만들 때 생긴 `Initial commit` 1개는 세지 않았습니다.

| 담당 | 커밋 수 | 커밋 목록 (머지 커밋도 함께 보임) |
|---|---|---|
| A @junhnno | 13 | https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/commits/develop?author=junhnno |
| B @Wattamelon | 14 | https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/commits/develop?author=Wattamelon |
| C @ADOHI | 34 | https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/commits/develop?author=ADOHI |

직접 세어 보는 명령입니다. 작성자 이름별로 커밋 수가 나옵니다.

```bash
git shortlog -sn --no-merges df6226b
```

커밋 메시지는 `feat:`, `fix:`, `docs:`, `test:`, `chore:` 접두어로 통일했습니다.

> **한 문장**: "머지 커밋을 빼고 A 13개, B 14개, C 34개로 모두 10개를 넘습니다."

#### (5) 문서의 팀 역할과 개인별 작업 요약

**요구**: 문서에 팀 역할과 개인별 작업 요약이 있고, Git 이력과 크게 어긋나지 않아야 한다.

**구현**: [README 11장](../README.md#11-팀-구성원-역할-및-개인별-작업-요약)에 담당자별 커밋 수, PR 번호, PR 마다 한 일을 적었습니다. 역할과 파일 소유는 [`docs/team-roles.md` L3–L15](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/docs/team-roles.md#L3-L15) 에 있습니다. PR 번호와 브랜치 이름을 그대로 적어서 GitHub 기록과 대조할 수 있습니다.

> **한 문장**: "README 11장에 담당자별 PR 번호와 작업 내용을 적어 Git 이력과 대조할 수 있게 했습니다."

---

## 6. 제약 사항

### 6-1. 민감정보 및 설정 관리

담당 A (설정 구조), C (배포 설정·문서)

이 프로젝트의 민감정보는 세 가지입니다.

| 이름 | 용도 | 로컬에서 | 배포 서버에서 |
|---|---|---|---|
| `SECRET_KEY` | 세션 쿠키 서명 | `.env` | Render 가 생성 |
| `AI_API_KEY` | AI API 호출 | `.env` | 대시보드에서 직접 입력 |
| `ADMIN_PASSWORD` | 관리자 페이지 | `.env` | Render 가 생성 |

SQLite 는 파일이라 DB 비밀번호가 없습니다. 사용자 비밀번호는 해시로만 저장합니다 ([4-2 (1)](#4-2-사용자-인증-및-접근-제어)).

#### (1) 코드와 문서에 직접 쓰지 않는다

**요구**: API 키 등 민감정보를 코드나 문서에 직접 적지 않는다.

**구현**: 코드에는 변수의 **이름**만 있고 값은 없습니다.

```python
# 세션 쿠키 서명용 키. 기본값을 두지 않아 .env 에 없으면 시작 시 오류가 난다.
secret_key: str
session_max_age_seconds: int = 60 * 60 * 24
# HTTPS 로 서비스할 때만 true. HTTP 배포에서 true 로 두면 쿠키가 전송되지 않아 로그인이 안 된다.
session_cookie_secure: bool = False

# AI 키는 앱의 인증/헬스체크 기능까지 막지 않도록 설정 단계에서는 선택값으로 읽는다.
# 실제 AI 호출에 키가 반드시 필요한지는 AI 클라이언트를 생성할 때 검사한다.
ai_api_key: SecretStr | None = None
ai_base_url: str = "https://copa.codyssey.kr/v1"
ai_model: str = "gpt-5.4"
ai_timeout_seconds: float = 20

# 관리자 페이지(/admin) 비밀번호. 비어 있으면 관리자 페이지를 끈다(404). (C 가 추가)
admin_password: SecretStr | None = None
```

→ [`config.py` L13–L27](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/config.py#L13-L27)

- `secret_key` 는 기본값이 없습니다. 값이 없으면 서버가 시작하지 않으므로, 약한 기본 키로 돌아가는 일이 없습니다
- 예시 파일에는 자리표시자와 빈 값만 있습니다 ([`.env.example` L7–L9](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/.env.example#L7-L9), [`.env.example` L18–L19](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/.env.example#L18-L19))
- 배포 설정에도 값이 없습니다. Render 가 만들거나 사람이 대시보드에 입력합니다

```yaml
- key: SECRET_KEY
  generateValue: true     # 세션 쿠키 서명 키. Render 가 생성
- key: ADMIN_PASSWORD
  generateValue: true     # 관리자 페이지(/admin) 비밀번호. Render 가 생성 (사용자명은 admin)
- key: AI_API_KEY
  sync: false             # 배포 시 대시보드에서 입력
```

→ [`render.yaml` L27–L32](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/render.yaml#L27-L32)

**확인**: `.env` 와 DB 파일은 한 번도 커밋되지 않았습니다. 아래 명령의 출력이 비어 있습니다. PR 템플릿의 체크리스트에도 "비밀 값이 코드·문서에 없다" 항목이 있습니다.

```bash
git log --all --diff-filter=A --oneline -- .env "*.db"
```

> **한 문장**: "코드와 배포 설정에는 변수 이름만 있고, 값은 로컬의 `.env` 와 Render 의 환경 변수에만 있습니다."

#### (2) 환경 변수로 관리한다

**요구**: 모든 민감정보는 환경 변수(`.env` 등)로 관리한다.

**구현**: 설정을 읽는 곳은 `config.py` 한 곳입니다. `.env` 파일과 실제 환경 변수를 읽어 `settings` 객체 하나로 만듭니다. 둘 다 있으면 실제 환경 변수가 우선합니다.

```python
    # .env 에 아직 정의하지 않은 다른 팀원의 설정이 있어도 오류 없이 무시한다.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
```

→ [`config.py` L29–L37](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/config.py#L29-L37)

다른 코드는 환경 변수를 직접 읽지 않고 `settings` 를 통해서만 값을 씁니다. 예: AI 클라이언트 [`ai_client.py` L85–L94](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/ai_client.py#L85-L94), 세션 설정 [`main.py` L32–L38](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/main.py#L32-L38), 관리자 인증 [`routers/pages.py` L45–L47](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/pages.py#L45-L47).

> **한 문장**: "설정은 `config.py` 가 환경 변수에서 한 번만 읽고, 나머지 코드는 그 객체를 통해서만 사용합니다."

#### (3) `.env` 는 `.gitignore` 로 제외한다

**요구**: `.env` 파일이 저장소에 올라가지 않도록 `.gitignore` 를 적용한다.

**구현**:

```gitignore
# 환경 변수 / 비밀 값 (절대 커밋하지 않음)
.env
.env.*
!.env.example

# 로컬 DB 파일
*.db
*.sqlite
*.sqlite3
```

→ [`.gitignore` L1–L9](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/.gitignore#L1-L9)

`.env` 와 `.env.local` 같은 변형은 모두 제외하고, 예시 파일 `.env.example` 만 예외로 허용합니다. 로컬 DB 파일도 함께 제외합니다.

**확인**: 저장소가 추적하는 파일 중 이름에 `.env` 가 들어간 것은 `.env.example` 하나입니다.

```bash
git ls-files | grep -i "\.env"
```

> **한 문장**: "`.gitignore` 가 `.env` 와 DB 파일을 제외하고, 예시 파일만 저장소에 올립니다."

#### (4) README 에 환경 변수 목록과 설정 방법을 적는다

**요구**: README 에 환경 변수 키 목록(이름 수준)과 설정 방법을 포함한다.

**구현**: [README 7장](../README.md#7-환경-변수)에 변수 9개의 이름, 필수 여부, 기본값, 설명을 표로 적었습니다. 값을 어디에 두는지는 [README 8장](../README.md#8-민감정보-관리)에, `.env` 를 만드는 순서는 [README 5장](../README.md#5-실행-방법-로컬)에 있습니다.

> **한 문장**: "README 7장에 환경 변수 9개를 표로 정리했고, 값은 적지 않았습니다."

### 6-2. 운영 안정성

담당 B

#### (1) AI 호출 타임아웃과 실패 안내

**요구**: AI API 호출에 타임아웃을 설정하고, 실패하면 사용자에게 오류 안내를 돌려준다.

**구현**: 제한 시간은 **20초**입니다. 환경 변수 `AI_TIMEOUT_SECONDS` 로 바꿀 수 있습니다 ([`config.py` L24](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/config.py#L24)). AI 클라이언트를 만들 때 이 값을 넘깁니다.

```python
client = AsyncOpenAI(
    api_key=api_key.get_secret_value(),
    base_url=settings.ai_base_url,
    timeout=settings.ai_timeout_seconds,
    max_retries=0,
)
```

→ [`ai_client.py` L89–L94](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/ai_client.py#L89-L94)

- `max_retries=0` 은 라이브러리의 자동 재시도(기본 2회)를 끈 것입니다. 재시도가 켜져 있으면 사용자가 기다리는 시간이 제한 시간의 몇 배가 될 수 있습니다
- 시간을 넘기면 `AITimeoutError` 로 바뀌고 ([`ai_client.py` L60–L61](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/ai_client.py#L60-L61)), 채팅 API 가 `504 AI_TIMEOUT` 과 안내 문구를 돌려줍니다 ([`routers/chat.py` L88–L99](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/app/routers/chat.py#L88-L99))
- 화면에는 "AI 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요. (error: AI_TIMEOUT)" 이 오류 말풍선으로 나옵니다

**확인**: [`test_chat_timeout_returns_504_and_logs_failure`](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/blob/df6226b1f8f5499a890b8b67219dfc5d073cfd4a/tests/test_chat.py#L265-L281)

> **한 문장**: "AI 호출은 20초로 제한하고 자동 재시도를 꺼서, 시간을 넘기면 504 와 안내 문구를 돌려줍니다."

#### (2) 처리 단계별 로그

**요구**: 요청 수신, AI 호출·응답, DB 저장 성공·실패가 로그로 남아야 한다.

**구현**: [4-5 (1)](#4-5-운영-및-유지보수)과 같은 내용입니다. 이벤트 여섯 가지(`request_received`, `ai_call_start`, `ai_call_success`, `ai_call_fail`, `db_save_success`, `db_save_fail`)가 같은 `request_id` 로 묶여 남습니다.

### 6-3. 협업 규칙

담당 전원

| 요구 | 대응 | 위치 |
|---|---|---|
| PR 기반으로 머지하고, 브랜치와 PR 기록이 저장소에 남는다 | 머지된 PR 22개, 기능 브랜치 18개 | [4-7 (2), (3)](#4-7-협업-및-형상관리) |
| 팀원별 의미 있는 커밋 10회 이상 | A 13, B 14, C 34 | [4-7 (4)](#4-7-협업-및-형상관리) |
| 기술 문서에 팀 역할과 개인별 작업 요약 | README 11장 | [4-7 (5)](#4-7-협업-및-형상관리) |

---

## 알려진 한계

질문을 받으면 숨기지 않고 답할 수 있도록 정리했습니다.

| 한계 | 내용 | 관련 항목 |
|---|---|---|
| API 키가 없는 서버에서의 채팅 오류 | `AI_API_KEY` 가 설정되지 않으면 입력 검증보다 먼저 `500` 이 납니다. B 의 영역이라 고치지 않고 [이슈 #20](https://github.com/Codyssey-AI-Chatbot/Codyssey-AI-Chatbot/issues/20) 으로 전달했고, 아직 열려 있습니다. 키가 설정된 배포 서버에서는 일어나지 않습니다 | 4-5 (4) |
| 자바스크립트 자동 테스트 없음 | 테스트는 서버 응답만 검증합니다. 화면 동작은 브라우저에서 직접 확인했습니다 | 4-1 (2), 4-5 (3) |
| PR 승인 기록 없음 | 규칙은 승인 후 머지였지만 GitHub 승인 기록은 남지 않았습니다 | 4-7 (3) |
| 배포 서버의 데이터 유지 | Render 무료 플랜은 서버가 잠들거나 다시 배포되면 SQLite 파일이 사라집니다 | 4-4 (1), 4-6 (1) |
| SQL 스크립트는 로컬 전용 | Render 무료 플랜에는 서버에 접속해 명령을 실행하는 기능이 없습니다 | 4-4 (3) |
| 문맥의 길이 제한 | 최근 5개라는 개수로만 제한하고 토큰 수는 세지 않습니다 | 4-3 (3) |
| 관리자 페이지 시도 횟수 제한 없음 | 길고 무작위인 비밀번호에 의존합니다 | 4-4 (3) |

## 함께 보면 좋은 문서

- [README](../README.md): 전체 기술 문서
- [퍼실 문답 예상 Q&A](facilitator-qna.md): 예상 질문과 답변
- [C 역할 작업 설명서](role-c-walkthrough.md): C 가 만든 코드의 상세 설명
- [팀 역할 분담과 협업 규칙](team-roles.md)
