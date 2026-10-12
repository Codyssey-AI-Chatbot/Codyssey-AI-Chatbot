// 상단 바의 로그아웃 버튼. A 의 POST /api/auth/logout 을 호출한 뒤 로그인 페이지로 이동한다.
// base.html 이 로그인한 화면에서만 이 파일을 불러온다. (버튼이 그때만 있기 때문)
document.getElementById("logout-button").addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.assign("/login");
});
