// 채팅 화면: 질문을 POST /api/chat 으로 보내고 답변을 같은 화면에 말풍선으로 추가한다.
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

async function sendMessage(message) {
  appendBubble("user", message);

  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  const data = await response.json();
  appendBubble("assistant", data.answer);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
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
