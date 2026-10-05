/* 开局界面。
 *
 * 负责身份选择、属性分配、人设表单与人设预览。**所有选项都从 /api/options 拿**——
 * 以后加身份、调属性点数、改人设字段，只改后端，这里不用动。
 *
 * 开局成功后通过 onStart 回调把结果交给 app.js，两边不共享内部状态。
 */

const els = {
  setup: document.getElementById("setup"),
  heroName: document.getElementById("hero-name"),
  identities: document.getElementById("identities"),
  customField: document.getElementById("custom-identity-field"),
  customInput: document.getElementById("custom-identity"),
  attributeField: document.getElementById("attribute-field"),
  allocator: document.getElementById("allocator"),
  pointsLeft: document.getElementById("points-left"),
  worlds: document.getElementById("worlds"),
  worldBox: document.getElementById("world-box"),
  worldName: document.getElementById("world-name"),
  worldTone: document.getElementById("world-tone"),
  worldDetails: document.getElementById("world-details"),
  worldKeywords: document.getElementById("world-keywords"),
  generateWorld: document.getElementById("generate-world"),
  worldHint: document.getElementById("world-hint"),
  worldPreview: document.getElementById("world-preview"),
  worldFacts: document.getElementById("world-facts"),
  regenerateWorld: document.getElementById("regenerate-world"),
  closeWorldPreview: document.getElementById("close-world-preview"),
  personaFields: document.getElementById("persona-fields"),
  completePersona: document.getElementById("complete-persona"),
  previewButton: document.getElementById("preview-persona"),
  personaHint: document.getElementById("persona-hint"),
  preview: document.getElementById("persona-preview"),
  previewFacts: document.getElementById("preview-facts"),
  previewAttrs: document.getElementById("preview-attrs"),
  regenerate: document.getElementById("regenerate"),
  closePreview: document.getElementById("close-preview"),
  start: document.getElementById("start"),
  hint: document.getElementById("setup-hint"),
  savesField: document.getElementById("saves-field"),
  saves: document.getElementById("saves"),
};

const CUSTOM = "自定义";

const state = {
  identities: [],
  identity: "",
  custom: false,
  attributes: {},
  points: 10,
  range: [1, 5],
  attributeNames: [],
  worlds: [],
  tones: [],
  world: null,
  worldFromPreset: true,
  fields: [],
  preview: null,
  busy: false,
};

function setHint(text, isError = false) {
  els.hint.textContent = text;
  els.hint.classList.toggle("error", isError);
}

function pick(container, label, note, active, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "choice" + (active ? " active" : "");

  const name = document.createElement("span");
  name.textContent = label;
  button.appendChild(name);
  if (note) {
    const small = document.createElement("small");
    small.textContent = note;
    button.appendChild(small);
  }

  button.addEventListener("click", () => {
    for (const child of container.children) child.classList.remove("active");
    button.classList.add("active");
    onClick();
  });
  return button;
}

/* ================= 选项加载 ================= */
export async function loadOptions() {
  const response = await fetch("/api/options");
  const data = await response.json();

  state.identities = data.identities || [];
  state.points = data.attribute_points ?? 10;
  state.range = data.attribute_range ?? [1, 5];
  state.fields = data.persona_fields || [];
  state.attributeNames = data.attribute_names || [];
  state.worlds = data.worlds || [];
  state.tones = data.tones || [];

  // 默认选中第一个身份和第一个世界
  state.identity = state.identities.length ? state.identities[0].name : "行者";
  state.world = state.worlds.length ? { ...state.worlds[0] } : null;
  state.worldFromPreset = true;

  renderIdentities();
  renderWorlds();
  renderPersonaFields();
  resetAttributes();
}

function renderIdentities() {
  els.identities.replaceChildren();
  for (const item of state.identities) {
    const note = Object.entries(item.attributes)
      .map(([name, value]) => `${name}${value}`)
      .join(" · ");
    els.identities.appendChild(
      pick(els.identities, item.name, note, item.name === state.identity, () => {
        state.custom = false;
        state.identity = item.name;
        els.customField.hidden = true;
        els.attributeField.hidden = true;
      })
    );
  }

  // 「自定义」放最后：选了之后自己分配属性
  els.identities.appendChild(
    pick(els.identities, CUSTOM, "自己分配属性", false, () => {
      state.custom = true;
      els.customField.hidden = false;
      els.attributeField.hidden = false;
      resetAttributes();
      els.customInput.focus();
    })
  );
}

function renderWorlds() {
  els.worlds.replaceChildren();
  for (const world of state.worlds) {
    const active = state.worldFromPreset && state.world && state.world.name === world.name;

    const card = document.createElement("button");
    card.type = "button";
    card.className = "world-card" + (active ? " active" : "");

    const name = document.createElement("span");
    name.className = "w-name";
    name.textContent = world.name;

    const pitch = document.createElement("span");
    pitch.className = "w-pitch";
    pitch.textContent = world.pitch;

    card.append(name, pitch);

    if (world.tone) {
      const tone = document.createElement("span");
      tone.className = "w-tone";
      tone.textContent = world.tone;
      card.appendChild(tone);
    }

    card.addEventListener("click", () => {
      state.world = { ...world };
      state.worldFromPreset = true;
      renderWorlds();
      els.worldBox.open = false;
    });

    els.worlds.appendChild(card);
  }
}

/* ================= 属性分配 ================= */
function resetAttributes() {
  // 从「每项都取平均值」起步，剩余的点数交给玩家自己加
  const base = Math.floor(state.points / 4);
  state.attributes = {};
  for (const name of state.attributeNames) state.attributes[name] = base;
  renderAllocator();
}

function spent() {
  return Object.values(state.attributes).reduce((sum, value) => sum + value, 0);
}

function renderAllocator() {
  const left = state.points - spent();
  els.pointsLeft.textContent = `剩余 ${left} 点`;

  els.allocator.replaceChildren();
  for (const name of state.attributeNames) {
    const li = document.createElement("li");

    const label = document.createElement("span");
    label.className = "name";
    label.textContent = name;

    const dec = document.createElement("button");
    dec.type = "button";
    dec.textContent = "−";
    dec.disabled = state.attributes[name] <= state.range[0];
    dec.addEventListener("click", () => adjust(name, -1));

    const value = document.createElement("span");
    value.className = "value";
    value.textContent = String(state.attributes[name]);

    const inc = document.createElement("button");
    inc.type = "button";
    inc.textContent = "+";
    inc.disabled = left <= 0 || state.attributes[name] >= state.range[1];
    inc.addEventListener("click", () => adjust(name, 1));

    const bar = document.createElement("span");
    bar.className = "bar";
    const fill = document.createElement("span");
    fill.style.width = `${(state.attributes[name] / state.range[1]) * 100}%`;
    bar.appendChild(fill);

    li.append(label, dec, value, inc, bar);
    els.allocator.appendChild(li);
  }
}

function adjust(name, delta) {
  const next = state.attributes[name] + delta;
  if (next < state.range[0] || next > state.range[1]) return;
  if (delta > 0 && spent() >= state.points) return;
  state.attributes[name] = next;
  renderAllocator();
}

/* ================= 人设表单 ================= */
function renderPersonaFields() {
  els.personaFields.replaceChildren();
  for (const field of state.fields) {
    const row = document.createElement("div");
    row.className = "row";

    const label = document.createElement("label");
    const name = document.createElement("span");
    name.className = "label";
    name.textContent = field.label;
    label.appendChild(name);
    if (field.hint) {
      const hint = document.createElement("span");
      hint.className = "hint-text";
      hint.textContent = field.hint;
      label.appendChild(hint);
    }

    // 来历通常要写两三句，给个多行的
    const input = document.createElement(field.key === "background" ? "textarea" : "input");
    input.id = `pf-${field.key}`;
    input.maxLength = field.key === "background" ? 300 : 80;
    input.placeholder = "留空由 GM 决定";
    if (field.key === "background") input.rows = 2;

    row.append(label, input);
    els.personaFields.appendChild(row);
  }
}

function collectFields() {
  const fields = {};
  for (const field of state.fields) {
    const input = document.getElementById(`pf-${field.key}`);
    const value = (input?.value || "").trim();
    if (value) fields[field.key] = value;
  }
  return fields;
}

function fieldsFromPreview(preview) {
  const fields = {};
  for (const field of state.fields) {
    const value = (preview[field.key] || "").trim();
    if (value) fields[field.key] = value;
  }
  if (preview.title) fields.title = preview.title;
  return fields;
}

/* ================= 人设预览 ================= */
function renderPreview(persona) {
  state.preview = persona;
  els.preview.hidden = false;

  els.previewFacts.replaceChildren();
  const rows = [
    ["称号", persona.title],
    ["外貌", persona.appearance],
    ["性格", persona.personality],
    ["目标", persona.motivation],
    ["来历", persona.background],
    ["特质", persona.trait],
  ];
  for (const [label, value] of rows) {
    if (!value) continue;
    const li = document.createElement("li");
    const tag = document.createElement("span");
    tag.className = "label";
    tag.textContent = label;
    const text = document.createElement("span");
    text.textContent = value;
    li.append(tag, text);
    els.previewFacts.appendChild(li);
  }

  if (persona.attributes) {
    const summary = Object.entries(persona.attributes)
      .map(([name, value]) => `${name} ${value}`)
      .join(" · ");
    els.previewAttrs.textContent = `建议属性：${summary}`;
  } else {
    els.previewAttrs.textContent = "";
  }
}

/* ================= 世界观 ================= */
function renderWorldPreview(world) {
  els.worldPreview.hidden = false;
  els.worldFacts.replaceChildren();

  const rows = [
    ["世界名", world.name],
    ["基调", world.tone],
    ["钩子", world.pitch],
    ["设定", world.details],
  ];
  for (const [label, value] of rows) {
    if (!value) continue;
    const li = document.createElement("li");
    const tag = document.createElement("span");
    tag.className = "label";
    tag.textContent = label;
    const text = document.createElement("span");
    text.textContent = value;
    li.append(tag, text);
    els.worldFacts.appendChild(li);
  }
}

async function generateWorld() {
  if (state.busy) return;
  state.busy = true;
  els.generateWorld.disabled = true;
  els.worldHint.textContent = "GM 正在构建世界……";
  els.worldHint.classList.remove("error");

  try {
    const response = await fetch("/api/world/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keywords: els.worldKeywords.value.trim(),
        name: els.worldName.value.trim(),
        tone: els.worldTone.value.trim(),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);

    // 生成结果回填到表单：玩家还能在生成的基础上手改
    const world = data.world;
    els.worldName.value = world.name || "";
    els.worldTone.value = world.tone || "";
    els.worldDetails.value = world.details || "";

    state.world = { ...world };
    state.worldFromPreset = false;
    renderWorlds();
    renderWorldPreview(world);
    els.worldHint.textContent = "";
  } catch (err) {
    els.worldHint.textContent = `生成失败：${err.message}`;
    els.worldHint.classList.add("error");
  } finally {
    state.busy = false;
    els.generateWorld.disabled = false;
  }
}

async function generatePreview() {
  if (state.busy) return;
  state.busy = true;
  els.previewButton.disabled = true;
  setHint("GM 正在构思角色……");

  try {
    const response = await fetch("/api/persona/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: els.heroName.value.trim() || "无名者",
        background: currentIdentity(),
        fields: collectFields(),
        attributes: state.custom ? state.attributes : null,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);

    renderPreview(data.persona);
    setHint("");
  } catch (err) {
    setHint(`生成失败：${err.message}`, true);
  } finally {
    state.busy = false;
    els.previewButton.disabled = false;
  }
}

function currentIdentity() {
  if (state.custom) {
    return (els.customInput.value.trim() || CUSTOM).slice(0, 16);
  }
  return state.identity;
}

/* ================= 开局 ================= */
function buildRequest() {
  const usePreview = state.preview !== null;

  let attributes = null;
  if (state.custom) {
    attributes = { ...state.attributes };
  } else if (usePreview && state.preview.attributes) {
    // 没自定义身份时，采纳 GM 按人设给的建议
    attributes = state.preview.attributes;
  }

  return {
    name: els.heroName.value.trim() || "无名者",
    background: currentIdentity(),
    world: collectWorld(),
    attributes,
    persona_fields: usePreview ? fieldsFromPreview(state.preview) : collectFields(),
    // 已经在预览里补全过了，就不必再调一次模型
    complete_persona: usePreview ? false : els.completePersona.checked,
  };
}

/**
 * 决定用哪份世界观。
 *
 * 展开了「自己写一个」并填了内容就以表单为准，否则用选中的卡片。
 * 这样后端只需要处理「一个名字」或「一整份内容」两种情况。
 */
function collectWorld() {
  const custom = {
    name: els.worldName.value.trim(),
    tone: els.worldTone.value.trim(),
    details: els.worldDetails.value.trim(),
  };
  if (custom.name || custom.details) {
    return { ...custom, origin: "user" };
  }
  return state.world;
}

export async function startGame(onStart) {
  if (state.custom && spent() !== state.points) {
    setHint(`属性还没分配完：还剩 ${state.points - spent()} 点`, true);
    return;
  }

  els.start.disabled = true;
  setHint("GM 正在开场……");

  try {
    const response = await fetch("/api/game/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildRequest()),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);

    setHint("");
    onStart(data.game);
  } catch (err) {
    setHint(`开局失败：${err.message}`, true);
  } finally {
    els.start.disabled = false;
  }
}

/* ================= 存档 ================= */
function formatTime(seconds) {
  if (!seconds) return "";
  const date = new Date(seconds * 1000);
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getMonth() + 1}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export async function refreshSaves(onLoad) {
  try {
    const response = await fetch("/api/saves");
    const data = await response.json();
    const saves = data.saves || [];

    els.saves.replaceChildren();
    els.savesField.hidden = saves.length === 0;

    for (const item of saves) {
      const li = document.createElement("li");

      const info = document.createElement("div");
      info.className = "info";
      info.title = "点击继续这一局";

      const name = document.createElement("span");
      name.className = "name";
      name.textContent = `${item.hero || "无名者"} · ${item.scenario || "未知剧本"}`;

      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = `第 ${item.turns} 回合 · ${formatTime(item.updated_at)}`;

      info.append(name, meta);
      info.addEventListener("click", () => loadSave(item.file, onLoad));

      const remove = document.createElement("button");
      remove.className = "del";
      remove.textContent = "删除";
      remove.addEventListener("click", () => deleteSave(item.file, onLoad));

      li.append(info, remove);
      els.saves.appendChild(li);
    }
  } catch {
    els.savesField.hidden = true;
  }
}

async function loadSave(file, onLoad) {
  setHint("正在读取存档……");
  try {
    const response = await fetch("/api/game/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);

    setHint("");
    onLoad(data.game);
  } catch (err) {
    setHint(`读档失败：${err.message}`, true);
  }
}

async function deleteSave(file, onLoad) {
  try {
    const response = await fetch("/api/game/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    await refreshSaves(onLoad);
  } catch (err) {
    setHint(`删除失败：${err.message}`, true);
  }
}

/* ================= 组装 ================= */
export function initSetup({ onStart, onLoad }) {
  els.start.addEventListener("click", () => startGame(onStart));
  els.generateWorld.addEventListener("click", generateWorld);
  els.regenerateWorld.addEventListener("click", generateWorld);
  els.closeWorldPreview.addEventListener("click", () => {
    els.worldPreview.hidden = true;
  });
  els.previewButton.addEventListener("click", generatePreview);
  els.regenerate.addEventListener("click", generatePreview);
  els.closePreview.addEventListener("click", () => {
    els.preview.hidden = true;
    state.preview = null;
  });
  els.completePersona.addEventListener("change", () => {
    els.previewButton.disabled = !els.completePersona.checked;
  });

  return {
    show() {
      els.setup.hidden = false;
      els.preview.hidden = true;
      state.preview = null;
      setHint("");
    },
    hide() {
      els.setup.hidden = true;
    },
    setHint,
    refreshSaves: () => refreshSaves(onLoad),
  };
}
