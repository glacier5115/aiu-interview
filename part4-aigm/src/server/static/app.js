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
  npcs: document.getElementById("npcs"),
  facts: document.getElementById("facts"),
  items: document.getElementById("items"),
  notes: document.getElementById("notes"),
  meta: document.getElementById("meta"),
  groupPersona: document.getElementById("group-persona"),
  groupTraits: document.getElementById("group-traits"),
  groupStatus: document.getElementById("group-status"),
  groupRelations: document.getElementById("group-relations"),
  groupNpcs: document.getElementById("group-npcs"),
  groupFacts: document.getElementById("group-facts"),
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
  // 生成中不禁用按钮，而是让它变成「停止」——随时可以打断
  els.submit.textContent = value ? "停止" : "行动";
  els.submit.classList.toggle("danger", value);
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

  // 先把玩家的行动和空气泡摆出来，文字一到就往里填
  const turn = startTurn(text);

  const controller = new AbortController();
  state.abort = controller;

  try {
    const response = await fetch("/api/game/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: state.gameId, action: text }),
      signal: controller.signal,
    });
    if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

    await consumeTurn(response.body, turn);
  } catch (err) {
    if (err.name === "AbortError") {
      appendTurnNotice(turn, "已停止生成");
    } else {
      appendTurnNotice(turn, `这一轮没能继续：${err.message}`);
    }
    // 中途停止时后端会把这轮的改动退回去，所以重新取一次状态对齐
    await refreshState();
  } finally {
    state.abort = null;
    setBusy(false);
    els.action.focus();
  }
}

/** 摆出一个「进行中」的回合：玩家的行动 + 一个待填充的叙事段落。 */
function startTurn(playerText) {
  const hint = els.log.querySelector(".empty");
  if (hint) hint.remove();

  const wrap = document.createElement("div");
  wrap.className = "turn";

  const act = document.createElement("div");
  act.className = "act";
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = "你";
  const body = document.createElement("span");
  body.textContent = playerText;
  act.append(who, body);

  const narration = document.createElement("div");
  narration.className = "narration streaming";
  const paragraph = document.createElement("p");
  narration.appendChild(paragraph);

  wrap.append(act, narration);
  els.log.appendChild(wrap);
  scrollToBottom();

  return { wrap, narration, paragraph };
}

/** 订阅回合的事件流。和对话那边用的是同一套 SSE 解析。 */
async function consumeTurn(body, turn) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop(); // 最后一段可能不完整，留到下一轮
    for (const event of events) handleTurnEvent(event, turn);
  }
  if (buffer.trim()) handleTurnEvent(buffer, turn);
}

function handleTurnEvent(rawEvent, turn) {
  const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data:"));
  if (!dataLine) return;

  let event;
  try {
    event = JSON.parse(dataLine.slice(5).trim());
  } catch {
    return; // 半截报文，交给下一轮缓冲拼接
  }

  switch (event.type) {
    case "delta":
      if (event.reset) {
        // reset 表示这一段要替换而不是追加
        turn.narration.replaceChildren();
        turn.paragraph = document.createElement("p");
        turn.narration.appendChild(turn.paragraph);
      }
      appendStreamText(turn, event.text);
      scrollToBottom();
      break;

    case "check":
      turn.narration.classList.remove("streaming");
      insertDice(turn.wrap, event.check);
      break;

    case "changes":
      insertChanges(turn.wrap, event.changes);
      break;

    case "done":
      turn.narration.classList.remove("streaming");
      // 用后端的完整状态重绘，把流式过程中的临时节点替换掉，保证两边一致
      renderAll(event.game);
      break;

    case "error":
      turn.narration.classList.remove("streaming");
      appendTurnNotice(turn, event.message);
      break;
  }
}

/** 往叙事区追加流式文本，遇到空行就另起一段。 */
function appendStreamText(turn, text) {
  const parts = text.split("\n\n");
  parts.forEach((part, index) => {
    if (index > 0) {
      turn.paragraph = document.createElement("p");
      turn.narration.appendChild(turn.paragraph);
    }
    turn.paragraph.textContent += part;
  });
}

function insertDice(wrap, check) {
  const dice = document.createElement("div");
  dice.className = "dice" + (check.success ? "" : " fail");
  dice.textContent = check.description;
  wrap.appendChild(dice);
  scrollToBottom();
}

function insertChanges(wrap, changes) {
  if (!changes || !changes.length) return;
  const box = document.createElement("div");
  box.className = "changes";
  for (const item of changes) {
    const chip = document.createElement("span");
    chip.textContent = item;
    box.appendChild(chip);
  }
  wrap.appendChild(box);
  scrollToBottom();
}

function appendTurnNotice(turn, text) {
  turn.narration.classList.remove("streaming");
  const notice = document.createElement("div");
  notice.className = "gameover";
  notice.textContent = text;
  turn.wrap.appendChild(notice);
  scrollToBottom();
}

/** 重新拉一次当前进度。中断或出错后用它对齐状态。 */
async function refreshState() {
  try {
    const response = await fetch("/api/game/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: state.gameId }),
    });
    if (!response.ok) return;
    const data = await response.json();
    renderAll(data.game);
  } catch {
    /* 拉不到就保持现状，总比把界面清空好 */
  }
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
  const personaFacts = [
    ["外貌", persona.appearance],
    ["性格", persona.personality],
    ["目标", persona.motivation],
    ["来历", persona.background],
  ].filter(([, value]) => value);

  els.persona.replaceChildren();
  for (const [label, value] of personaFacts) {
    const li = document.createElement("li");
    const tag = document.createElement("span");
    tag.className = "label";
    tag.textContent = label;
    const text = document.createElement("span");
    text.textContent = value;
    li.append(tag, text);
    els.persona.appendChild(li);
  }
  els.groupPersona.hidden = personaFacts.length === 0;

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

  // 人物图鉴：秘密字段后端不会下发，只给一句「有事瞒着」的提示
  const npcs = game.npcs || [];
  els.npcs.replaceChildren();
  for (const npc of npcs) {
    const li = document.createElement("li");
    li.className = "npc";

    const head = document.createElement("div");
    head.className = "npc-head";
    const name = document.createElement("span");
    name.className = "npc-name";
    name.textContent = npc.name;
    const attitude = document.createElement("span");
    attitude.className = "npc-attitude";
    attitude.textContent = npc.attitude;
    head.append(name, attitude);

    const meta = document.createElement("div");
    meta.className = "npc-meta";
    meta.textContent = [npc.identity, npc.motive].filter(Boolean).join(" · ");

    li.append(head, meta);
    if (npc.has_secret) {
      const hint = document.createElement("span");
      hint.className = "npc-secret";
      hint.textContent = "有事瞒着";
      li.appendChild(hint);
    }
    els.npcs.appendChild(li);
  }
  els.groupNpcs.hidden = npcs.length === 0;

  // 已知事实：这些不参与摘要压缩，会一直带着
  const facts = game.facts || [];
  fillList(els.facts, facts, "还没有确定下来的事");
  els.groupFacts.hidden = facts.length === 0;

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

  els.submit.addEventListener("click", () => {
    // 生成中这个按钮是「停止」
    if (state.busy && state.abort) {
      state.abort.abort();
    } else {
      act();
    }
  });
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
