# -*- coding: utf-8 -*-
"""report_html.py — Markdown 报告 → 单文件 HTML（学术产品化呈现，演示门面）

把本技能各模块产出的 Markdown 报告（AutoReport 分析报告 / 申报书体检报告 /
引文核验报告等）转换为可双击打开的可视化 HTML 单文件：

- 图片自动 base64 内嵌（真单文件，可直接发送/投屏，无外部依赖）
- 表格斑马纹、自适应；「风险等级：高/中/低」自动渲染为彩色风险卡片
- ✓ / ⚠ 等状态符号自动着色；中文学术排版、打印友好

用法：
  python tools/report_html.py 报告.md                    # 同目录输出 报告.html
  python tools/report_html.py 报告.md -o 输出.html       # 指定输出路径
  python tools/report_html.py 报告.md --title "自定义标题"

设计边界：转换器只做呈现，不改动报告任何内容；解析失败的行按原样输出，
保证信息零丢失。

> AI生成
"""

import argparse
import base64
import html
import mimetypes
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 样式（内嵌，无外部依赖；学术蓝主色 + 风险语义色）
# ---------------------------------------------------------------------------

_CSS = """
:root{
  --primary:#1a5fb4; --dark:#0d2b52; --line:#dbe4ee; --gray:#5a6b7d;
  --high:#c0392b; --high-bg:#fdeceb; --mid:#b95c00; --mid-bg:#fdf3e4;
  --low:#0b8a6d; --low-bg:#e8f6f0; --ok:#0b8a6d; --warn:#c0392b;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;
  color:#1d2a3a;background:#eef3f9;line-height:1.75;font-size:15px}
.page{max-width:920px;margin:0 auto;padding:34px 30px 60px}
.hero{background:linear-gradient(135deg,#0d2b52 0%,#1a5A8A 100%);
  color:#fff;border-radius:14px;padding:34px 36px;margin-bottom:26px}
.hero h1{font-size:27px;line-height:1.35;font-weight:700}
.hero .meta{margin-top:12px;font-size:13px;opacity:.85;line-height:1.9}
.hero .meta b{font-weight:600}
h2{font-size:21px;color:var(--dark);border-left:5px solid var(--primary);
  padding-left:12px;margin:30px 0 14px}
h3{font-size:17px;color:var(--dark);margin:20px 0 10px}
h4{font-size:15.5px;color:var(--dark);margin:16px 0 8px}
p{margin:9px 0}
ul,ol{margin:8px 0 8px 24px}
li{margin:4px 0}
img{max-width:100%;border:1px solid var(--line);border-radius:8px;
  margin:10px 0;display:block}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13.8px;
  background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(13,43,82,.07)}
th{background:var(--dark);color:#fff;padding:9px 12px;text-align:left;font-weight:600}
td{padding:8px 12px;border-bottom:1px solid #edf2f8}
tr:nth-child(even) td{background:#f7fafd}
tr:last-child td{border-bottom:none}
code{background:#eef2f7;border:1px solid #dde6ef;border-radius:4px;
  padding:1px 6px;font-family:Consolas,monospace;font-size:13px;color:#c7254e}
pre{background:#0d2b52;color:#e8eef7;border-radius:10px;padding:14px 16px;
  overflow-x:auto;margin:12px 0}
pre code{background:none;border:none;color:inherit;padding:0;font-size:13px}
blockquote{border-left:4px solid var(--primary);background:#fff;
  padding:10px 16px;margin:10px 0;border-radius:0 8px 8px 0;color:var(--gray)}
hr{border:none;border-top:1px solid var(--line);margin:22px 0}
/* 风险卡片：### [风险等级：高/中/低] … */
.risk{border-radius:10px;padding:14px 18px;margin:14px 0}
.risk h3{margin:0 0 6px;font-size:16px}
.risk-high{background:var(--high-bg);border:1px solid #f2c8c4;border-left:6px solid var(--high)}
.risk-high h3{color:var(--high)}
.risk-mid{background:var(--mid-bg);border:1px solid #eedcbe;border-left:6px solid var(--mid)}
.risk-mid h3{color:var(--mid)}
.risk-low{background:var(--low-bg);border:1px solid #cbe8dd;border-left:6px solid var(--low)}
.risk-low h3{color:var(--low)}
/* 状态符号着色 */
.ok{color:var(--ok);font-weight:600}
.bad{color:var(--warn);font-weight:600}
.warn{color:var(--mid);font-weight:600}
.note{font-size:13px;color:var(--gray);background:#fff;border:1px dashed var(--line);
  border-radius:8px;padding:10px 14px;margin:14px 0}
@media print{body{background:#fff}.page{padding:0}.hero{border-radius:0}}
"""

# ---------------------------------------------------------------------------
# Markdown → HTML（针对性支持本技能报告格式，解析失败按原样输出）
# ---------------------------------------------------------------------------

_RISK_RE = re.compile(r"^#{1,6}\s*\[?\s*风险等级[:：]?\s*(高|中|低)[^\]]*\]?\s*(.*)$")


def _inline(text):
    """行内元素：加粗/行内代码/链接/状态符号着色。"""
    s = html.escape(text)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    # 状态符号着色（报告内的 ✓ / ✗ / ⚠）
    s = s.replace("✓", '<span class="ok">✓</span>')
    s = s.replace("✔", '<span class="ok">✔</span>')
    s = s.replace("✗", '<span class="bad">✗</span>')
    s = s.replace("✘", '<span class="bad">✘</span>')
    s = re.sub(r"⚠(?![^<]*</span>)", '<span class="warn">⚠</span>', s)
    return s


def _img_to_dataurl(path, base_dir):
    """图片 → base64 data URL（找不到时返回 None，按原样保留）。"""
    p = Path(path)
    if not p.is_absolute():
        p = base_dir / p
    if not p.exists():
        return None
    mime = mimetypes.guess_type(str(p))[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _table(lines, start):
    """解析表格行（含分隔行），返回 (html, 结束索引)。"""
    rows = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|"):
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if not re.match(r"^[\s:|-]+$", lines[i].strip()):  # 跳过分隔行
            rows.append(cells)
        i += 1
    if not rows:
        return None, start
    out = ["<table>", "<tr>"]
    for c in rows[0]:
        out.append(f"<th>{_inline(c)}</th>")
    out.append("</tr>")
    for r in rows[1:]:
        out.append("<tr>")
        for c in r:
            out.append(f"<td>{_inline(c)}</td>")
        out.append("</tr>")
    out.append("</table>")
    return "\n".join(out), i


def _codeblock(lines, start):
    """解析 ``` 代码块，返回 (html, 结束索引)。"""
    lang = lines[start][3:].strip()
    body = []
    i = start + 1
    while i < len(lines) and not lines[i].strip().startswith("```"):
        body.append(lines[i])
        i += 1
    cls = f' class="language-{html.escape(lang)}"' if lang else ""
    return f"<pre><code{cls}>{html.escape(chr(10).join(body))}</code></pre>", i + 1


def md_to_html(md_text, base_dir, title=None):
    """Markdown → HTML 片段（图片内嵌、风险卡片、表格、代码块）。"""
    lines = md_text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        # 代码块
        if s.startswith("```"):
            block, i = _codeblock(lines, i)
            out.append(block)
            continue
        # 表格
        if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|?\s*$", lines[i + 1]):
            block, i = _table(lines, i)
            out.append(block)
            continue
        # 风险卡片（体检报告条目）
        m = _RISK_RE.match(s)
        if m:
            level, rest = m.group(1), m.group(2)
            cls = {"高": "risk-high", "中": "risk-mid", "低": "risk-low"}[level]
            out.append(f'<div class="risk {cls}"><h3>{_inline(f"[风险等级：{level}] " + rest)}</h3>')
            i += 1
            # 卡片体：吞掉紧随其来的非标题行
            while i < len(lines) and not lines[i].lstrip().startswith("#") \
                    and lines[i].strip() and not _RISK_RE.match(lines[i].strip()):
                out.append(f"<p>{_inline(lines[i].strip())}</p>")
                i += 1
            out.append("</div>")
            continue
        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            lv = min(len(m.group(1)) + 1, 6)  # 降一级，h1 留给页头
            out.append(f"<h{lv}>{_inline(m.group(2))}</h{lv}>")
            i += 1
            continue
        # 分隔线
        if re.match(r"^-{3,}$", s):
            out.append("<hr>")
            i += 1
            continue
        # 引用
        if s.startswith(">"):
            quote = s.lstrip(">").strip()
            out.append(f"<blockquote>{_inline(quote)}</blockquote>")
            i += 1
            continue
        # 图片（内嵌 base64）
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*(.*)$", s)
        if m:
            alt, src, cap = m.group(1), m.group(2), m.group(3)
            data = _img_to_dataurl(src, base_dir)
            use = data if data else html.escape(src)
            alt_h = html.escape(alt or "图")
            out.append(f'<img src="{use}" alt="{alt_h}">')
            if cap:
                out.append(f'<p class="note">{_inline(cap)}</p>')
            elif alt:
                out.append(f'<p class="note">{_inline(alt)}</p>')
            i += 1
            continue
        # 列表
        if re.match(r"^[-*]\s+", s):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i].strip()))
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(t)}</li>" for t in items) + "</ul>")
            continue
        if re.match(r"^\d+[.、]\s+", s):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+[.、]\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+[.、]\s+", "", lines[i].strip()))
                i += 1
            out.append("<ol>" + "".join(f"<li>{_inline(t)}</li>" for t in items) + "</ol>")
            continue
        # 空行
        if not s:
            i += 1
            continue
        # 普通段落（合并连续行）
        para = [s]
        i += 1
        while i < len(lines) and lines[i].strip() and \
                not re.match(r"^(#{1,6}\s|```|\||>|!\[|[-*]\s|\d+[.、]\s|---)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(out)


def _page_title(md_text, override=None):
    """页头标题：取第一个 # 行；正文不再重复渲染该行。"""
    m = re.search(r"^#\s+(.+)$", md_text, re.MULTILINE)
    return override or (m.group(1).strip() if m else "报告")


def _meta_from_md(md_text):
    """提取报告头部的元信息（- 生成时间：… 之类）作为 hero 副信息。"""
    metas = re.findall(r"^-\s+(.+?:.+)$", md_text.splitlines()[0:8] and
                       "\n".join(md_text.splitlines()[:10]), re.MULTILINE)
    return [m.strip() for m in metas][:4]


def render_file(md_path, out_path=None, title=None):
    """主入口：md 文件 → 单文件 HTML。返回输出路径。"""
    md_path = Path(md_path)
    if not md_path.exists():
        print(f"[error] 找不到 {md_path}")
        return None
    text = md_path.read_text(encoding="utf-8")
    h1 = _page_title(text, title)
    body = md_to_html(text, md_path.parent)
    meta_html = ""
    metas = _meta_from_md(text)
    if metas:
        meta_html = '<div class="meta">' + "<br>".join(_inline(m) for m in metas) + "</div>"
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(h1)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">
  <div class="hero"><h1>{_inline(h1)}</h1>{meta_html}</div>
  {body}
</div>
</body>
</html>
"""
    out = Path(out_path) if out_path else md_path.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out


def main():
    try:  # Windows GBK 控制台无法编码 ✓/⚠ 等符号：替换而非崩溃（v2.1.1）
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Markdown 报告 → 单文件 HTML（学术产品化呈现）")
    ap.add_argument("input", help="输入 .md 报告文件")
    ap.add_argument("-o", "--out", default=None, help="输出 .html 路径（默认同名）")
    ap.add_argument("--title", default=None, help="覆盖页头标题")
    args = ap.parse_args()
    out = render_file(args.input, args.out, args.title)
    if out:
        print(f"输出：{out}")
        size_kb = out.stat().st_size / 1024
        print(f"大小：{size_kb:.1f} KB（图片已 base64 内嵌，单文件可直接发送/投屏）")


if __name__ == "__main__":
    main()
