/* 界面逻辑。
 *
 * 前端只做两件事：
 *   1. 组织 UI —— 渲染消息、更新状态、处理输入、代码块复制
 *   2. 订阅后端推送的事件流 —— 收到什么就画什么
 *
 * 不拼接 prompt、不维护对话历史、不判断模型状态：这些都在后端。
 * 两者之间只有 HTTP + SSE 一种联系方式。
 */

import { renderMarkdown } from "./markdown.js";

const els = {
  messages: document.getElementById("messages"),
  thread: document.getElementById("thread"),
  input: document.getElementById("input"),
  send: document.getElementById("send"),
  clear: document.getElementById("clear"),
  theme: document.getElementById("theme"),
  status: document.getElementById("status"),
  dot: document.getElementById("status-dot"),
};

/* ================= 会话标识 ================= */
// 存在浏览器本地，后端据此找回对话上下文；换浏览器或清缓存即是一段新对话
const SESSION_KEY = "aiu.session_id";

function newSessionId() {
  // crypto.randomUUID 只在安全上下文（localhost 或 HTTPS）可用，这里留个降级
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return "s-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
}

const sessionId = localStorage.getItem(SESSION_KEY) || (() => {
  const id = newSessionId();
  localStorage.setItem(SESSION_KEY, id);
  return id;
})();

/* ================= 主题 ================= */
// 三态：跟随系统 / 浅色 / 深色。实际生效的值写在 <html data-theme> 上，样式见 style.css
const THEME_KEY = "aiu.theme";
const THEME_ORDER = ["system", "light", "dark"];
const THEME_LABEL = { system: "跟随系统", light: "浅色", dark: "深色" };
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

function themePref() {
  return localStorage.getItem(THEME_KEY) || "system";
}

function resolveTheme(pref) {
  if (pref === "light" || pref === "dark") return pref;
  return darkQuery.matches ? "dark" : "light";
}

function applyTheme(pref) {
  localStorage.setItem(THEME_KEY, pref);
  document.documentElement.dataset.theme = resolveTheme(pref);
  els.theme.textContent = THEME_LABEL[pref];
}

els.theme.addEventListener("click", () => {
  const next = THEME_ORDER[(THEME_ORDER.indexOf(themePref()) + 1) % THEME_ORDER.length];
  applyTheme(next);
});

// 选了「跟随系统」时，系统配色变了页面要跟着变
darkQuery.addEventListener("change", () => {
  if (themePref() === "system") {
    document.documentElement.dataset.theme = resolveTheme("system");
  }
});

els.theme.textContent = THEME_LABEL[themePref()];

/* ================= 消息渲染 ================= */
let busy = false;
let currentModel = "";

function atBottom() {
  return els.messages.scrollHeight - els.messages.scrollTop - els.messages.clientHeight < 60;
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

function clearHint() {
  const hint = els.thread.querySelector(".empty");
  if (hint) hint.remove();
}

/** 把气泡里累积的原文渲染成 HTML。 */
function renderBubble(bubble) {
  bubble.innerHTML = renderMarkdown(bubble._raw || "");
}

// 流式输出时每个增量都重渲染整段文本，用 requestAnimationFrame 合并同帧内的多次调用
const pendingBubbles = new Set();
let rafId = 0;

function scheduleRender(bubble) {
  pendingBubbles.add(bubble);
  if (rafId) return;
  rafId = requestAnimationFrame(() => {
    rafId = 0;
    const stick = atBottom(); // 渲染前判断，用户手动往上翻时不要把他拽回去
    for (const target of pendingBubbles) renderBubble(target);
    pendingBubbles.clear();
    if (stick) scrollToBottom();
  });
}

/** 追加一段增量文本。原文存在元素的 _raw 上，渲染只是它的投影。 */
function appendChunk(bubble, chunk) {
  bubble._raw = (bubble._raw || "") + chunk;
  scheduleRender(bubble);
}

/** 新建一个气泡。用户消息按纯文本显示，不做 Markdown 解析。 */
function addBubble(role, text = "") {
  clearHint();
  const row = document.createElement("div");
  row.className = "row " + role;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble._raw = text;
  row.appendChild(bubble);
  els.thread.appendChild(row);

  if (role === "assistant") renderBubble(bubble);
  else bubble.textContent = text;

  scrollToBottom();
  return bubble;
}

function setStatus(text, state) {
  els.status.textContent = text;
  els.dot.className = "dot" + (state ? " " + state : "");
}

function setBusy(value) {
  busy = value;
  els.send.disabled = value;
  els.send.textContent = value ? "生成中" : "发送";
}

/* ================= 事件流的订阅 ================= */
// 后端推的是 SSE 报文：以 "data: {json}" 为单位、空行分隔
function handleEvent(rawEvent, bubble) {
  const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data:"));
  if (!dataLine) return;

  let event;
  try {
    event = JSON.parse(dataLine.slice(5).trim());
  } catch {
    return; // 半截报文，留给下一轮缓冲拼接
  }

  if (event.type === "delta") {
    appendChunk(bubble, event.content);
  } else if (event.type === "error") {
    bubble.classList.add("error");
    appendChunk(bubble, event.message);
  }
  // type === "done" 表示本轮结束，不需要额外处理
}

async function consumeStream(body, bubble) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop(); // 最后一段可能不完整，留到下一轮
    for (const event of events) handleEvent(event, bubble);
  }
  if (buffer.trim()) handleEvent(buffer, bubble);
}

/* ================= 交互 ================= */
async function sendMessage() {
  const text = els.input.value.trim();
  if (!text || busy) return;

  setBusy(true);
  addBubble("user", text);
  const bubble = addBubble("assistant", "");
  bubble.classList.add("pending");

  els.input.value = "";
  autoGrow();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: text }),
    });
    if (!response.ok || !response.body) throw new Error("HTTP " + response.status);

    await consumeStream(response.body, bubble);
    if (currentModel) setStatus("已连接 · " + currentModel, "ok");
  } catch (err) {
    bubble.classList.add("error");
    bubble._raw = (bubble._raw || "") + "请求失败：" + err.message;
    setStatus("连接异常", "bad");
  } finally {
    bubble.classList.remove("pending");
    renderBubble(bubble); // 保证最终内容完整呈现
    scrollToBottom();
    setBusy(false);
    els.input.focus();
  }
}

async function resetSession() {
  try {
    const response = await fetch("/api/session/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
    if (!response.ok) throw new Error("HTTP " + response.status);
    els.thread.innerHTML =
      '<p class="empty"><strong>上下文已清空</strong>开始新的对话吧</p>';
  } catch {
    addBubble("assistant", "清空失败，请稍后再试。");
  }
}

/* ================= 代码块复制 ================= */
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return true;
  }
  // 非安全上下文（例如通过局域网 IP 访问）拿不到 clipboard API，退回旧办法
  const scratch = document.createElement("textarea");
  scratch.value = text;
  scratch.style.position = "fixed";
  scratch.style.opacity = "0";
  document.body.appendChild(scratch);
  scratch.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  scratch.remove();
  return ok;
}

// 复制按钮是渲染出来的，数量不定，统一用事件委托
els.thread.addEventListener("click", async (event) => {
  const button = event.target.closest(".copy-btn");
  if (!button) return;
  const code = button.closest(".code-wrap")?.querySelector("code");
  if (!code) return;

  const ok = await copyText(code.textContent);
  button.textContent = ok ? "已复制" : "复制失败";
  button.classList.toggle("copied", ok);
  setTimeout(() => {
    button.textContent = "复制";
    button.classList.remove("copied");
  }, 1600);
});

/* ================= 启动 ================= */
async function refreshStatus() {
  try {
    const response = await fetch("/api/health");
    const info = await response.json();
    currentModel = info.model || "";
    if (info.ok) setStatus("已连接 · " + info.model, "ok");
    else setStatus("模型服务未就绪", "bad");
  } catch {
    setStatus("后端服务不可用", "bad");
  }
}

function autoGrow() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 180) + "px";
}

els.input.addEventListener("input", autoGrow);
els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});
els.send.addEventListener("click", sendMessage);
els.clear.addEventListener("click", resetSession);

refreshStatus();
els.input.focus();
