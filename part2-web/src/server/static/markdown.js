/* 极简 Markdown 渲染器。
 *
 * 只处理对话场景里真正会用到的语法：围栏代码块、行内代码、粗体、斜体、
 * 标题、列表、引用、水平线、链接。
 *
 * 两个设计决定：
 *   1. 不引入 marked.js 之类的第三方库，整个前端不依赖 CDN，clone 下来就能跑。
 *   2. 先转义、再套格式。模型输出属于不可信内容，如果直接当成 HTML 插入页面，
 *      模型返回的 <script> 就会被浏览器真的执行。这里所有文本都先过 escapeHtml，
 *      之后的替换只会生成我们自己写死的受控标签，因此输出里不可能出现模型
 *      自带的标签。
 *
 * 不支持 `_斜体_`：下划线在代码和变量名里太常见（snake_case_name），
 * 认成斜体反而会破坏内容。
 */

const ESCAPE_MAP = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

/** HTML 转义。 */
export function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (ch) => ESCAPE_MAP[ch]);
}

/** 行内格式。传入的文本必须已经过 escapeHtml。 */
function renderInline(text) {
  return text
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(
      /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
    );
}

/** 段内换行转成 <br>。 */
function withBreaks(html) {
  return html.replace(/\n/g, "<br>");
}

/** 判断这一行是否开启一个块级结构。 */
function startsBlock(line) {
  return (
    /^\s*```/.test(line) ||
    /^#{1,4}\s+\S/.test(line) ||
    /^\s*(-{3,}|\*{3,})\s*$/.test(line) ||
    /^\s*>\s?/.test(line) ||
    /^\s*([-*+]|\d+\.)\s+\S/.test(line)
  );
}

/** 代码块：顶部一行放语言标记与复制按钮。 */
function codeBlock(code, lang) {
  const label = lang ? `<span class="code-lang">${escapeHtml(lang)}</span>` : "<span></span>";
  return (
    '<div class="code-wrap">' +
    `<div class="code-head">${label}` +
    '<button type="button" class="copy-btn">复制</button></div>' +
    `<pre><code>${escapeHtml(code)}</code></pre>` +
    "</div>"
  );
}

/** 把一段 Markdown 文本渲染成 HTML 字符串。 */
export function renderMarkdown(source) {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 围栏代码块。未闭合时（流式输出到一半）会把剩余内容整体当成代码，
    // 等后续增量补上收尾的 ``` 后自然恢复。
    const fence = line.match(/^\s*```(\S*)\s*$/);
    if (fence) {
      const lang = fence[1];
      const body = [];
      i += 1;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) {
        body.push(lines[i]);
        i += 1;
      }
      i += 1; // 跳过收尾的 ```
      out.push(codeBlock(body.join("\n"), lang));
      continue;
    }

    // 空行
    if (!line.trim()) {
      i += 1;
      continue;
    }

    // 标题：整体降三级，免得在气泡里出现超大字号
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const level = Math.min(heading[1].length + 2, 6);
      out.push(`<h${level}>${renderInline(escapeHtml(heading[2]))}</h${level}>`);
      i += 1;
      continue;
    }

    // 水平线
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      out.push("<hr>");
      i += 1;
      continue;
    }

    // 引用
    if (/^\s*>\s?/.test(line)) {
      const quoted = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quoted.push(lines[i].replace(/^\s*>\s?/, ""));
        i += 1;
      }
      const html = withBreaks(renderInline(escapeHtml(quoted.join("\n"))));
      out.push(`<blockquote>${html}</blockquote>`);
      continue;
    }

    // 列表
    if (/^\s*([-*+]|\d+\.)\s+\S/.test(line)) {
      const ordered = /^\s*\d+\.\s/.test(line);
      const items = [];
      while (i < lines.length && /^\s*([-*+]|\d+\.)\s+\S/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*+]|\d+\.)\s+/, ""));
        i += 1;
      }
      const tag = ordered ? "ol" : "ul";
      const body = items.map((item) => `<li>${renderInline(escapeHtml(item))}</li>`).join("");
      out.push(`<${tag}>${body}</${tag}>`);
      continue;
    }

    // 普通段落：吃掉连续的非空行
    const paragraph = [];
    while (i < lines.length && lines[i].trim() && !startsBlock(lines[i])) {
      paragraph.push(lines[i]);
      i += 1;
    }
    const html = withBreaks(renderInline(escapeHtml(paragraph.join("\n"))));
    out.push(`<p>${html}</p>`);
  }

  return out.join("");
}
