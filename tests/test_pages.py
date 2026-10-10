"""화면 라우트 테스트 (담당: C). 템플릿이 렌더링되고 접근 제어가 화면에도 적용되는지 확인한다."""


def test_index_redirects_to_chat(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/chat"


def test_signup_page_renders_form(client):
    response = client.get("/signup")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'data-api="/api/auth/signup"' in response.text
    assert "회원가입" in response.text


def test_login_page_renders_form(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert 'data-api="/api/auth/login"' in response.text
    assert "회원가입이 완료되었습니다" not in response.text


def test_login_page_shows_signup_notice(client):
    response = client.get("/login?signup=1")

    assert response.status_code == 200
    assert "회원가입이 완료되었습니다" in response.text


def test_static_stylesheet_is_served(client):
    response = client.get("/static/style.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


CREDENTIALS = {"username": "page_tester", "password": "correct-horse"}


def login(client):
    assert client.post("/api/auth/signup", json=CREDENTIALS).status_code == 201
    assert client.post("/api/auth/login", json=CREDENTIALS).status_code == 200


def test_chat_page_redirects_anonymous_user_to_login(client):
    response = client.get("/chat", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_chat_page_renders_for_logged_in_user(client):
    login(client)

    response = client.get("/chat")

    assert response.status_code == 200
    assert 'id="chat-form"' in response.text
    assert CREDENTIALS["username"] in response.text  # 상단 바에 사용자명 표시
