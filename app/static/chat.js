// 채팅 화면: 질문을 POST /api/chat 으로 보내고 답변을 같은 화면에 말풍선으로 추가한다.
// 성공 응답은 {"answer", "chat_id"}, 실패 응답은 {"error", "message"} (팀 합의 인터페이스).
const messagesBox = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("message");
const sendButton = document.getElementById("send-button");

function appendBubble(kind, text) {
  messagesBox.querySelector(".messages-empty")?.remove();
  const bubble = document.createElement("div");
  bubble.className = `bubble bubble-${kind}`;
  bubble.textContent = text;
  messagesBox.appendChild(bubble);
  messagesBox.scrollTop = messagesBox.scrollHeight;
  return bubble;
}

// 오류 말풍선: 안내 문구 뒤에 에러 코드를 붙여 사용자가 문의할 때 전달할 수 있게 한다.
function appendError(message, code) {
  const bubble = appendBubble("error", `${message} `);
  const codeTag = document.createElement("code");
  codeTag.textContent = `(error: ${code})`;
  bubble.appendChild(codeTag);
}

function setPending(pending) {
  input.disabled = pending;
  sendButton.disabled = pending;
  sendButton.textContent = pending ? "전송 중…" : "전송";
  if (!pending) input.focus();
}

async function sendMessage(message) {
  appendBubble("user", message);
  const loading = appendBubble("assistant", "답변을 생성하는 중…");
  setPending(true);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    if (response.status === 401) {
      // 세션이 만료된 경우. 메시지는 잃지만 로그인 화면으로 보낸다.
      window.location.assign("/login");
      return;
    }

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
  } catch {
    loading.remove();
    appendError("서버에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.", "NETWORK_ERROR");
  } finally {
    setPending(false);
  }
}

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

// Enter 는 전송, Shift+Enter 는 줄바꿈
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});
