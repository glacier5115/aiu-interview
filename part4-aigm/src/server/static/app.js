/* 游戏界面。
 *
 * 前端只做三件事：渲染叙事与角色卡、收集玩家输入、把后端给的状态画出来。
 * 掷骰、判定、状态修改全部在后端——前端拿到的永远只是结果。
 *
 * 开局表单在 setup.js 里，这个文件只管进游戏之后的事。
 */

import { initSetup, loadOptions } from "./setup.js";

// 把当前对局记在浏览器本地，刷新页面后能接回来
const RESUME_KEY = "aigm.game_id";

const els = {
  play: document.getElementById("play"),
  scenarioTitle: document.getElementById("scenario-title"),
  heroLine: document.getElementById("hero-line"),
  log: document.getElementById("log"),

  sheetName: document.getElementById("sheet-name"),
  sheetBackground: document.getElementById("sheet-background"),
  sheetTitle: document.getElementById("sheet-title"),
  hpFill: document.getElementById("hp-fill"),
  hpText: document.getElementById("hp-text"),
  attrs: document.getElementById("attrs"),
  persona: document.getElementById("persona"),
  traits: document.getElementById("traits"),
  statuses: document.getElementById("statuses"),
  relations: document.getElementById("relations"),
  items: document.getElementById("items"),
  notes: document.getElementById("notes"),
  meta: document.getElementById("meta"),
  groupPersona: document.getElementById("group-persona"),
  groupTraits: document.getElementById("group-traits"),
  groupStatus: document.getElementById("group-status"),
  groupRelations: document.getElementById("group-relations"),
  groupItems: document.getElementById("group-items"),
  groupNotes: document.getElementById("group-notes"),

  action: document.getElementById("action"),
  submit: document.getElementById("submit"),
  save: document.getElementById("save"),
  restart: document.getElementById("restart"),
  theme: document.getElementById("theme"),
};

const state = {
  gameId: null,
  lastGame: null,
  busy: false,
};

let setupUI = null;

/* ================= 主题 ================= */
const THEME_KEY = "aigm.theme";
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
darkQuery.addEventListener("change", () => {
  if (themePref() === "system") {
    document.documentElement.dataset.theme = resolveTheme("system");
  }
});
els.theme.textContent = THEME_LABEL[themePref()];

/* ================= 工具 ================= */
function scrollToBottom() {
  els.log.scrollTop = els.log.scrollHeight;
}

function autoGrow() {
  els.action.style.height = "auto";
  els.action.style.height = Math.min(els.action.scrollHeight, 150) + "px";
}

function setBusy(value) {
  state.busy = value;
  els.submit.disabled = value;
  els.submit.textContent = value ? "GM 思考中" : "行动";
}

function persist(gameId) {
  state.gameId = gameId;
  localStorage.setItem(RESUME_KEY, gameId);
}

function forget() {
  state.gameId = null;
  state.lastGame = null;
  localStorage.removeItem(RESUME_KEY);
}

/* ================= 进入游戏 ================= */
function enterPlay(game) {
  persist(game.id);
  els.play.hidden = false;
  setupUI.hide();
  renderAll(game);
  els.action.focus();
}

/**
 * 页面加载时把上一局接回来。
 *
 * 服务重启过的话内存里的对局就没了，这时会拿到 404——清掉本地记录、回到开局
 * 界面并说明原因，而不是让玩家对着一个坏掉的界面发呆。
 */
async function resume() {
  const saved = localStorage.getItem(RESUME_KEY);
  if (!saved) return false;

  try {
    const response = await fetch("/api/game/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: saved }),
    });
    if (!response.ok) throw new Error("gone");
    const data = await response.json();
    enterPlay(data.game);
    return true;
  } catch {
    forget();
    setupUI.setHint("上一局的进度已经不在了（服务可能重启过），重新开一局吧");
    return false;
  }
}

/* ================= 行动 ================= */
async function act() {
  const text = els.action.value.trim();
  if (!text || state.busy) return;

  setBusy(true);
  els.action.value = "";
  autoGrow();
  showPending(text);

  try {
    const response = await fetch("/api/game/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: state.gameId, action: text }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);

    renderAll(data.game);
  } catch (err) {
    renderAll(state.lastGame);
    appendNotice(`这一轮没能继续：${err.message}`);
  } finally {
    setBusy(false);
    els.action.focus();
  }
}

function showPending(actionText) {
  const wrap = document.createElement("div");
  wrap.className = "turn";

  const act = document.createElement("div");
  act.className = "act";
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = "你";
  const body = document.createElement("span");
  body.textContent = actionText;
  act.append(who, body);
  wrap.appendChild(act);

  const pending = document.createElement("div");
  pending.className = "pending";
  pending.textContent = "GM 正在思考";
  wrap.appendChild(pending);

  els.log.appendChild(wrap);
  scrollToBottom();
}

function appendNotice(text) {
  const notice = document.createElement("div");
  notice.className = "gameover";
  notice.textContent = text;
  els.log.appendChild(notice);
  scrollToBottom();
}

/* ================= 渲染 ================= */
function renderAll(game) {
  state.lastGame = game;
  updateHeader(game);
  renderLog(game);
  renderSheet(game);
}

function updateHeader(game) {
  els.scenarioTitle.textContent = game.scenario;
  els.heroLine.textContent =
    `${game.character.name} · 第 ${game.turn_count} 回合` +
    (game.over ? " · 冒险结束" : "");
}

function renderLog(game) {
  els.log.replaceChildren();

  if (game.opening) {
    const opening = document.createElement("div");
    opening.className = "opening";
    opening.textContent = game.opening;
    els.log.appendChild(opening);
  }

  for (const turn of game.turns) {
    els.log.appendChild(turnBlock(turn));
  }

  if (game.over) {
    const over = document.createElement("div");
    over.className = "gameover";
    over.textContent = "角色已经倒下，这场冒险到此为止。点「重开」开始新的旅程。";
    els.log.appendChild(over);
  }

  scrollToBottom();
}

function turnBlock(turn) {
  const wrap = document.createElement("div");
  wrap.className = "turn";

  const act = document.createElement("div");
  act.className = "act";
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = "你";
  const body = document.createElement("span");
  body.textContent = turn.player;
  act.append(who, body);
  wrap.appendChild(act);

  const narration = document.createElement("div");
  narration.className = "narration";
  for (const line of String(turn.narration || "").split(/\n+/).filter(Boolean)) {
    const paragraph = document.createElement("p");
    paragraph.textContent = line;
    narration.appendChild(paragraph);
  }
  wrap.appendChild(narration);

  if (turn.check) {
    const dice = document.createElement("div");
    dice.className = "dice" + (turn.check.success ? "" : " fail");
    dice.textContent = turn.check.description;
    wrap.appendChild(dice);
  }

  if (turn.changes && turn.changes.length) {
    const changes = document.createElement("div");
    changes.className = "changes";
    for (const item of turn.changes) {
      const chip = document.createElement("span");
      chip.textContent = item;
      changes.appendChild(chip);
    }
    wrap.appendChild(changes);
  }

  return wrap;
}

function renderSheet(game) {
  const character = game.character;

  els.sheetName.textContent = character.name;
  els.sheetBackground.textContent = character.background;
  els.sheetTitle.textContent = character.title || "";

  const ratio = character.hp_max ? character.hp / character.hp_max : 0;
  els.hpFill.style.width = `${Math.max(0, ratio * 100)}%`;
  els.hpFill.classList.toggle("low", ratio <= 0.34);
  els.hpText.textContent = `生命 ${character.hp} / ${character.hp_max}`;

  // 人设
  const persona = character.persona || {};
  const facts = [
    ["外貌", persona.appearance],
    ["性格", persona.personality],
    ["目标", persona.motivation],
    ["来历", persona.background],
  ].filter(([, value]) => value);

  els.persona.replaceChildren();
  for (const [label, value] of facts) {
    const li = document.createElement("li");
    const tag = document.createElement("span");
    tag.className = "label";
    tag.textContent = label;
    const text = document.createElement("span");
    text.textContent = value;
    li.append(tag, text);
    els.persona.appendChild(li);
  }
  els.groupPersona.hidden = facts.length === 0;

  // 特质
  const traits = persona.traits || [];
  els.traits.replaceChildren();
  for (const trait of traits) {
    const li = document.createElement("li");
    li.textContent = trait;
    els.traits.appendChild(li);
  }
  els.groupTraits.hidden = traits.length === 0;

  // 状态
  const statuses = character.statuses || [];
  els.statuses.replaceChildren();
  for (const status of statuses) {
    const li = document.createElement("li");
    li.className = "chip";
    li.textContent = status.name;
    if (status.turns > 0) {
      const turns = document.createElement("span");
      turns.className = "turns";
      turns.textContent = `${status.turns} 回合`;
      li.appendChild(turns);
    }
    els.statuses.appendChild(li);
  }
  els.groupStatus.hidden = statuses.length === 0;

  // 属性
  els.attrs.replaceChildren();
  for (const item of character.attributes) {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = item.name;
    const value = document.createElement("span");
    value.textContent = String(item.value);
    const mod = document.createElement("span");
    mod.className = "mod";
    mod.textContent = item.modifier >= 0 ? `+${item.modifier}` : String(item.modifier);
    li.append(name, value, mod);
    els.attrs.appendChild(li);
  }

  // 关系
  const relations = character.relations || [];
  els.relations.replaceChildren();
  for (const relation of relations) {
    const li = document.createElement("li");
    li.className = "relation";
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = relation.target;
    const attitude = document.createElement("span");
    attitude.className = "attitude";
    attitude.textContent = relation.attitude;
    li.append(who, attitude);
    els.relations.appendChild(li);
  }
  els.groupRelations.hidden = relations.length === 0;

  // 物品与线索
  fillList(els.items, character.inventory, "空手");
  fillList(els.notes, character.notes, "还没有线索");

  // 本次冒险
  els.meta.replaceChildren();
  for (const text of [`回合 ${game.turn_count}`, game.scenario]) {
    const li = document.createElement("li");
    li.textContent = text;
    els.meta.appendChild(li);
  }
}

function fillList(container, values, emptyText) {
  container.replaceChildren();
  if (!values || !values.length) {
    const li = document.createElement("li");
    li.className = "none";
    li.textContent = emptyText;
    container.appendChild(li);
    return;
  }
  for (const value of values) {
    const li = document.createElement("li");
    li.textContent = value;
    container.appendChild(li);
  }
}

/* ================= 存档与重开 ================= */
async function saveGame() {
  if (!state.gameId) return;
  els.save.disabled = true;
  try {
    const response = await fetch("/api/game/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: state.gameId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    appendNotice(`已存档：${data.file}（第 ${data.turn_count} 回合）`);
  } catch (err) {
    appendNotice(`存档失败：${err.message}`);
  } finally {
    els.save.disabled = false;
  }
}

function restart() {
  forget();
  els.play.hidden = true;
  els.log.replaceChildren();
  setupUI.show();
  setupUI.refreshSaves();
}

/* ================= 启动 ================= */
async function boot() {
  setupUI = initSetup({
    onStart: (game) => enterPlay(game),
    onLoad: (game) => enterPlay(game),
  });

  try {
    await loadOptions();
    setupUI.refreshSaves();
  } catch {
    setupUI.setHint("无法获取开局选项，请确认服务在运行", true);
  }

  els.submit.addEventListener("click", act);
  els.save.addEventListener("click", saveGame);
  els.restart.addEventListener("click", restart);

  els.action.addEventListener("input", autoGrow);
  els.action.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      act();
    }
  });

  if (!(await resume())) {
    setupUI.show();
    els.action.blur();
  }
}

boot();
