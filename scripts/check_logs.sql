-- 대화 로그 확인용 SQL (평가자/운영자용)
--
-- 실행 방법
--   sqlite3 CLI 가 있을 때 : sqlite3 -header -column app.db < scripts/check_logs.sql
--   CLI 가 없을 때(Windows): python scripts/check_logs.py [app.db]
--
-- 테이블: users(id, username, password_hash, created_at)
--         chat_logs(id, user_id -> users.id, question, answer, created_at)
-- 시각은 UTC 로 저장되어 있다. (한국 시각 = +9시간)

-- 1) 최근 대화 로그 20건: 누가, 언제, 무엇을 물었고 어떤 답을 받았는지
SELECT
    c.id,
    u.username,
    c.created_at,
    substr(c.question, 1, 60) AS question,
    substr(c.answer, 1, 60)   AS answer
FROM chat_logs AS c
JOIN users AS u ON u.id = c.user_id
ORDER BY c.created_at DESC, c.id DESC
LIMIT 20;

-- 2) 사용자별 대화 수와 마지막 대화 시각 (사용자 기준 추적)
SELECT
    u.id              AS user_id,
    u.username,
    COUNT(c.id)       AS chat_count,
    MAX(c.created_at) AS last_chat_at
FROM users AS u
LEFT JOIN chat_logs AS c ON c.user_id = u.id
GROUP BY u.id, u.username
ORDER BY chat_count DESC, u.id;
