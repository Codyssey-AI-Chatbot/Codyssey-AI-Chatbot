// 회원가입/로그인 폼 공통 처리.
// <form data-api="/api/auth/..." data-next="/이동할/경로"> 의 입력값을 JSON 으로 보내고,
// 성공하면 data-next 로 이동, 실패하면 서버가 준 {"error", "message"} 의 message 를 보여 준다.
document.querySelectorAll("form[data-api]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const errorBox = form.querySelector(".form-error");
    const submitButton = form.querySelector("button[type=submit]");
    const body = Object.fromEntries(new FormData(form));

    errorBox.textContent = "";

    // 회원가입 화면의 비밀번호 확인란은 서버로 보내지 않고 화면에서만 비교한다.
    if ("password_confirm" in body) {
      if (body.password !== body.password_confirm) {
        errorBox.textContent = "비밀번호가 서로 일치하지 않습니다.";
        return;
      }
      delete body.password_confirm;
    }

    submitButton.disabled = true;
    try {
      const response = await fetch(form.dataset.api, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (response.ok) {
        window.location.assign(form.dataset.next);
        return;
      }
      const data = await response.json().catch(() => null);
      errorBox.textContent = data?.message ?? `요청에 실패했습니다. (HTTP ${response.status})`;
    } catch {
      errorBox.textContent = "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
    } finally {
      submitButton.disabled = false;
    }
  });
});
