/**
 * Cloudflare Worker — News Relay Admin API
 *
 * Маршруты:
 *   GET  /              → index.html (обрабатывается Assets binding)
 *   GET  /api/status    → { channels, keywords }
 *   GET  /api/channels  → string[]
 *   POST /api/channels  → { handle }  → добавить
 *   DELETE /api/channels/:handle → удалить
 *   GET  /api/keywords  → string[]
 *   POST /api/keywords  → { word }   → добавить
 *   DELETE /api/keywords           → очистить все
 *   DELETE /api/keywords/:word     → удалить одно
 *
 * Авторизация: заголовок X-Init-Data с Telegram WebApp initData.
 * Проверяется HMAC-SHA256 подпись; user.id должен совпасть с ADMIN_TG_ID.
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // CORS для Telegram WebView
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Init-Data",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    if (url.pathname.startsWith("/api/")) {
      const response = await handleAPI(request, env, url);
      // Добавляем CORS-заголовки к каждому API-ответу
      Object.entries(corsHeaders).forEach(([k, v]) => response.headers.set(k, v));
      return response;
    }

    // Всё остальное отдаёт Assets (index.html)
    return env.ASSETS.fetch(request);
  },
};

// ── Роутер API ────────────────────────────────────────────────────────────────

async function handleAPI(request, env, url) {
  // Авторизация — обязательна для всех API-запросов
  const initData = request.headers.get("X-Init-Data") || "";
  const authErr = await checkAuth(initData, env);
  if (authErr) return authErr;

  const path = url.pathname;          // /api/channels, /api/keywords/foo, ...
  const method = request.method;

  // /api/status
  if (path === "/api/status" && method === "GET") {
    return jsonOK({
      channels: await kvGet(env.KV, "channels"),
      keywords: await kvGet(env.KV, "keywords"),
    });
  }

  // /api/channels
  if (path === "/api/channels") {
    if (method === "GET")  return jsonOK(await kvGet(env.KV, "channels"));
    if (method === "POST") return addItem(request, env.KV, "channels", normalizeChannel);
  }

  // /api/channels/:handle  (handle может содержать @, /, т.д.)
  const chanMatch = path.match(/^\/api\/channels\/(.+)$/);
  if (chanMatch && method === "DELETE") {
    return deleteItem(env.KV, "channels", normalizeChannel(decodeURIComponent(chanMatch[1])));
  }

  // /api/keywords
  if (path === "/api/keywords") {
    if (method === "GET")    return jsonOK(await kvGet(env.KV, "keywords"));
    if (method === "POST")   return addItem(request, env.KV, "keywords", w => w.trim().toLowerCase());
    if (method === "DELETE") return clearAll(env.KV, "keywords");
  }

  // /api/keywords/:word
  const kwMatch = path.match(/^\/api\/keywords\/(.+)$/);
  if (kwMatch && method === "DELETE") {
    return deleteItem(env.KV, "keywords", decodeURIComponent(kwMatch[1]).toLowerCase());
  }

  return jsonError(404, "Not Found");
}

// ── Telegram initData валидация ───────────────────────────────────────────────

async function checkAuth(initDataStr, env) {
  if (!initDataStr) return jsonError(401, "X-Init-Data header отсутствует");

  try {
    const user = await validateInitData(initDataStr, env.BOT_TOKEN);
    if (!user) return jsonError(401, "Неверная подпись initData");

    const adminId = parseInt(env.ADMIN_TG_ID, 10);
    if (user.id !== adminId) return jsonError(403, "Доступ запрещён");

    return null; // ok
  } catch (e) {
    return jsonError(401, `Ошибка авторизации: ${e.message}`);
  }
}

async function validateInitData(initDataStr, botToken) {
  const params = new URLSearchParams(initDataStr);
  const hash = params.get("hash");
  if (!hash) return null;
  params.delete("hash");

  const dataCheckString = [...params.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");

  const enc = new TextEncoder();

  // secret_key = HMAC-SHA256("WebAppData", bot_token)
  const baseKey = await crypto.subtle.importKey(
    "raw", enc.encode("WebAppData"),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const secretBytes = await crypto.subtle.sign("HMAC", baseKey, enc.encode(botToken));

  // expected_hash = HMAC-SHA256(secret_key, data_check_string)
  const checkKey = await crypto.subtle.importKey(
    "raw", secretBytes,
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sigBytes = await crypto.subtle.sign("HMAC", checkKey, enc.encode(dataCheckString));

  const expectedHash = [...new Uint8Array(sigBytes)]
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");

  if (expectedHash !== hash) return null;

  const userStr = params.get("user");
  return userStr ? JSON.parse(userStr) : {};
}

// ── KV-хелперы ────────────────────────────────────────────────────────────────

async function kvGet(kv, key) {
  const raw = await kv.get(key);
  return raw ? JSON.parse(raw) : [];
}

async function kvSet(kv, key, value) {
  await kv.put(key, JSON.stringify(value));
}

// ── CRUD-операции ─────────────────────────────────────────────────────────────

async function addItem(request, kv, key, normalize) {
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonError(400, "Невалидный JSON");
  }

  const raw = (body.handle ?? body.word ?? "").toString().trim();
  if (!raw) return jsonError(400, "Пустое значение");

  const value = normalize(raw);
  const list = await kvGet(kv, key);

  if (list.includes(value)) {
    return jsonError(409, `'${value}' уже существует`);
  }

  list.push(value);
  await kvSet(kv, key, list);
  return jsonOK({ added: value }, 201);
}

async function deleteItem(kv, key, value) {
  const list = await kvGet(kv, key);
  const next = list.filter(i => i !== value);
  if (next.length === list.length) {
    return jsonError(404, `'${value}' не найдено`);
  }
  await kvSet(kv, key, next);
  return jsonOK({ deleted: value });
}

async function clearAll(kv, key) {
  const list = await kvGet(kv, key);
  await kvSet(kv, key, []);
  return jsonOK({ deleted: list.length });
}

// ── Утилиты ───────────────────────────────────────────────────────────────────

function normalizeChannel(handle) {
  let h = handle.trim().toLowerCase();
  if (h.startsWith("https://t.me/")) h = "@" + h.slice("https://t.me/".length);
  if (!h.startsWith("@")) h = "@" + h;
  return h;
}

function jsonOK(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function jsonError(status, detail) {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
