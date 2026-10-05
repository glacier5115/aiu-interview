/* 视觉检测页。
 *
 * 后端返回的是**结构化数据**——每个框的坐标、类别、置信度；这里负责把它画出来：
 * 框的位置、颜色、标签样式全部由前端决定。后端不生成任何图片或 HTML 片段，
 * 所以想换成画在 canvas 上、或者做成表格，都不用动后端。
 */

const els = {
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("file-input"),
  stage: document.getElementById("stage"),
  preview: document.getElementById("preview"),
  overlay: document.getElementById("overlay"),
  detections: document.getElementById("detections"),
  reportMeta: document.getElementById("report-meta"),
  resetBtn: document.getElementById("reset-image"),
  hint: document.getElementById("vision-hint"),
};

const MAX_BYTES = 10 * 1024 * 1024;

// 按类别分配颜色：同一类别每次都是同一个颜色，看起来才稳定
const PALETTE = [
  "#ef4444", "#f59e0b", "#10b981", "#3b82f6",
  "#8b5cf6", "#ec4899", "#14b8a6", "#f97316",
];

function colorFor(label) {
  let hash = 0;
  for (const ch of label) {
    hash = (hash * 31 + ch.codePointAt(0)) % 99991;
  }
  return PALETTE[hash % PALETTE.length];
}

function setHint(text, isError = false) {
  els.hint.textContent = text;
  els.hint.classList.toggle("error", isError);
}

/* ================= 上传与检测 ================= */
async function detectFile(file) {
  if (!file) return;

  if (!file.type.startsWith("image/")) {
    setHint("请选择图片文件（JPG / PNG）", true);
    return;
  }
  if (file.size > MAX_BYTES) {
    const mb = (file.size / 1024 / 1024).toFixed(1);
    setHint(`图片过大（${mb} MB），上限 10 MB`, true);
    return;
  }

  // 先把图片显示出来，让用户立刻看到反馈，而不是干等
  showImage(URL.createObjectURL(file));
  setHint("正在检测…");

  const form = new FormData();
  form.append("file", file);

  try {
    const response = await fetch("/api/detect", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
    render(data);
    setHint("");
  } catch (err) {
    clearResult();
    setHint(`检测失败：${err.message}`, true);
  }
}

function showImage(url) {
  if (els.preview.src.startsWith("blob:")) {
    URL.revokeObjectURL(els.preview.src);
  }
  els.preview.src = url;
  els.dropzone.hidden = true;
  els.stage.hidden = false;
}

/* ================= 渲染 ================= */
function render(result) {
  els.overlay.replaceChildren();
  els.detections.replaceChildren();

  for (const det of result.detections) {
    els.overlay.appendChild(makeBox(det, result.width, result.height));
  }

  if (result.detections.length === 0) {
    const item = document.createElement("li");
    item.className = "none";
    item.textContent = "未检测到目标";
    els.detections.appendChild(item);
  } else {
    for (const det of result.detections) {
      els.detections.appendChild(makeItem(det));
    }
  }

  const fps = result.elapsed_ms > 0 ? Math.round(1000 / result.elapsed_ms) : 0;
  els.reportMeta.textContent =
    `${result.width}×${result.height} · ${result.detections.length} 个目标 · ` +
    `${result.elapsed_ms.toFixed(1)} ms（约 ${fps} FPS）`;
}

/** 一个检测框。用百分比定位，所以图片缩放时框会跟着走。 */
function makeBox(det, width, height) {
  const [x1, y1, x2, y2] = det.box;
  const color = colorFor(det.label);

  const box = document.createElement("div");
  box.className = "bbox";
  box.style.left = `${(x1 / width) * 100}%`;
  box.style.top = `${(y1 / height) * 100}%`;
  box.style.width = `${((x2 - x1) / width) * 100}%`;
  box.style.height = `${((y2 - y1) / height) * 100}%`;
  box.style.borderColor = color;

  const tag = document.createElement("span");
  tag.className = "bbox-tag";
  tag.style.background = color;
  tag.textContent = `${det.label} ${Math.round(det.confidence * 100)}%`;

  box.appendChild(tag);
  return box;
}

/** 结果列表里的一行。 */
function makeItem(det) {
  const item = document.createElement("li");

  const dot = document.createElement("span");
  dot.className = "swatch";
  dot.style.background = colorFor(det.label);

  const name = document.createElement("span");
  name.className = "name";
  name.textContent = det.label;

  const score = document.createElement("span");
  score.className = "score";
  score.textContent = `${(det.confidence * 100).toFixed(1)}%`;

  // 用 textContent 而不是 innerHTML：类别名虽然来自固定词表，但保持这个习惯
  item.append(dot, name, score);
  return item;
}

function clearResult() {
  els.overlay.replaceChildren();
  els.detections.replaceChildren();
  els.reportMeta.textContent = "";
}

function resetImage() {
  clearResult();
  setHint("");
  els.stage.hidden = true;
  els.dropzone.hidden = false;
  els.fileInput.value = "";
  if (els.preview.src.startsWith("blob:")) {
    URL.revokeObjectURL(els.preview.src);
    els.preview.removeAttribute("src");
  }
}

/* ================= 事件 ================= */
els.dropzone.addEventListener("click", () => els.fileInput.click());
els.fileInput.addEventListener("change", () => detectFile(els.fileInput.files[0]));
els.resetBtn.addEventListener("click", resetImage);

for (const type of ["dragenter", "dragover"]) {
  els.dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    els.dropzone.classList.add("dragging");
  });
}
for (const type of ["dragleave", "drop"]) {
  els.dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    els.dropzone.classList.remove("dragging");
  });
}
els.dropzone.addEventListener("drop", (event) => {
  detectFile(event.dataTransfer?.files?.[0]);
});

/* ================= 启动时确认检测能力 ================= */
export async function init() {
  try {
    const response = await fetch("/api/health");
    const info = await response.json();
    if (info.vision && info.vision.ready) {
      setHint(`检测模型：${info.vision.model}`);
      return;
    }
    els.dropzone.classList.add("disabled");
    setHint(
      "检测模型未就绪。请先在 part3-yolo 目录下训练一次生成权重，然后重启本服务。",
      true
    );
  } catch {
    setHint("无法获取服务状态", true);
  }
}
