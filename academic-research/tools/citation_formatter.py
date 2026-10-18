# -*- coding: utf-8 -*-
"""
citation_formatter.py — GB/T 7714 参考文献批量格式化脚本（academic-research 技能 v1.4）

把任意混乱引文（知网/万方/EndNote 导出、手打条目）批量转为 GB/T 7714-2015 规范格式：

    ①字段解析：作者串｜年份｜标题｜来源｜卷(期)｜页码｜DOI（中西文分别处理，全半角归一）
    ②类型判定：期刊[J]/学位论文[D]/专著[M]/电子资源[EB/OL]…（特征规则，附判定依据与置信度）
    ③国标重排：>3位作者截断加"等/et al."、西文姓前名缩写、标点规范、页码连字符
    ④输出三件套：规范条目 + 原文-规范对照表 + 质量报告（低置信/解析失败单独列出）

设计原则：
  1. 默认即满意初版：零参数调用 = 顺序编码制国标输出
  2. 规则用代码不用模型：格式化是规则性任务，同一输入永远同一输出（零漂移）
  3. 诚信机制：判定置信度分级，低置信标"待人工复核"，不假装完美
  4. 学术红线：本工具只做格式整理，不校验文献真伪（真伪核验见指南智能体工作流）

用法：
  python citation_formatter.py input.txt                      # 零参数：国标顺序编码制
  python citation_formatter.py input.txt --style author_year  # 著者-出版年制
  python citation_formatter.py input.txt --out_format csv     # 对照表 CSV 版
  python citation_formatter.py --demo                         # 用 samples/ 数据自验
"""

import argparse
import re
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TOOLS_DIR.parent
SAMPLES = SKILL_ROOT / "samples"
DEFAULT_OUT = Path(".temp") / "citations"

# ---------------------------------------------------------------------------
# 基础工具：全半角归一、语言判定
# ---------------------------------------------------------------------------

_FULL2HALF = {
    "，": ",", "。": ".", "．": ".", "；": ";", "：": ":",
    "（": "(", "）": ")", "［": "[", "］": "]", "【": "[", "】": "]",
    "－": "-", "—": "-", "–": "-", "～": "~", "　": " ", "％": "%",
}


def _normalize(text):
    """全角标点归一为半角（供解析用；输出时按国标规则重新上标点）。"""
    for k, v in _FULL2HALF.items():
        text = text.replace(k, v)
    return re.sub(r"\s+", " ", text).strip()


def _is_western(text):
    """判断引文主体语言：西文（拉丁字母占比高）→ True。"""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    western = sum(1 for c in letters if ord(c) < 0x2E80)  # 拉丁/希腊/西里尔区之前
    return western / len(letters) > 0.5


def _contains_cjk(text):
    return any(0x2E80 <= ord(c) < 0x9FFF or 0x3400 <= ord(c) < 0x4DBF for c in text)


# ---------------------------------------------------------------------------
# ① 字段解析
# ---------------------------------------------------------------------------

# 常见文献类型标识（用户已打标时直接采信）
TYPE_MARKS = {
    "J": "期刊论文", "M": "专著", "D": "学位论文", "C": "会议论文",
    "N": "报纸文章", "P": "专利", "S": "标准", "R": "报告", "A": "档案",
    "EB/OL": "电子资源", "DB/OL": "在线数据库", "J/OL": "网络期刊",
}


def _parse_year(text):
    m = re.search(r"(19|20)\d{2}", text)
    return m.group(0) if m else None


def _parse_doi(text):
    m = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.IGNORECASE)
    return m.group(0).rstrip(". ") if m else None


def _split_authors(author_str):
    """作者串拆分：兼容 中/英逗号、顿号、分号、空格+and。"""
    s = _normalize(author_str)
    s = re.sub(r"\s+and\s+", "; ", s, flags=re.IGNORECASE)
    parts = re.split(r"[;,，；、]", s)
    return [p.strip() for p in parts if p.strip()]


def _fmt_western_author(name):
    """西文作者 → 姓前名缩写：'John Smith' → 'SMITH J'；'Smith, John' → 'SMITH J'；
    'Smith J'（已是姓前名缩写，姓+单个大写缩写）→ 'SMITH J'。"""
    name = _normalize(name).strip()
    if "," in name:
        family, given = name.split(",", 1)
    else:
        tokens = name.split()
        if len(tokens) == 1:
            return name.upper()
        # 已是姓前名缩写：末 token 为单字母缩写（SMITH J / HINTON G E）
        if all(re.fullmatch(r"[A-Z]\.?", t) for t in tokens[1:]):
            family = tokens[0]
            given = " ".join(tokens[1:])
        else:
            family, given = tokens[-1], " ".join(tokens[:-1])
    family = family.strip().upper()
    initials = " ".join(g[0].upper() + "." for g in given.strip().split() if g)
    # 国标缩写不带点：SMITH J（GB/T 7714-2015 示例格式）
    initials = initials.replace(".", "")
    return f"{family} {initials}".strip()


def _fmt_chinese_author(name):
    """中文作者：直接用全名。"""
    return _normalize(name)


def _parse_citation(raw):
    """单条引文 → 结构化字段 dict。解析容错：缺失字段为 None，不抛异常。

    策略：先全文抽取确定性字段（DOI/年份/卷期/页码/URL/类型标识），
    再按"作者段. 标题段. 来源段"骨架切分剩余文本，并从各段中剥离
    已抽取字段，避免重复拼接（v1.4 首轮实测修复）。
    """
    text = _normalize(raw)
    d = {"raw": raw.strip(), "normalized": text, "authors": [],
         "year": None, "title": None, "source": None,
         "volume": None, "issue": None, "pages": None, "doi": None,
         "url": None, "publisher": None, "city": None, "type_mark": None,
         "access_date": None, "pub_date": None}

    # ---- 确定性字段抽取（并从正文剥离） ----
    body = re.sub(r"^\[\d+\]\s*", "", text)  # 去掉开头 [n] 序号

    d["doi"] = _parse_doi(body)
    if d["doi"]:
        body = body.replace(d["doi"], " ").strip()

    m = re.search(r"https?://\S+", body)
    if m:
        d["url"] = m.group(0).rstrip(".，。")
        body = body.replace(d["url"], " ").strip()

    # 类型标识 [J]/[EB/OL]…（采信第一个）
    m = re.search(r"\[([A-Z]{1,2}(?:/OL)?)\]", body)
    if m and m.group(1) in TYPE_MARKS:
        d["type_mark"] = m.group(1)

    # 年份：优先"发布日期(日期)"或括号内日期；否则取 4 位年份（保护标准号/专利号场景：
    # 若年份嵌在"GB/T xxxx-yyyy"或"CNxxxx"内则跳过该匹配继续找）
    m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", body)
    if m:
        d["pub_date"] = m.group(1)
    m = re.search(r"\[(\d{4}-\d{2}-\d{2})\]", body)
    if m:
        d["access_date"] = m.group(1)
    for ym in re.finditer(r"(19|20)\d{2}", body):
        y = ym.group(0)
        prefix = body[max(0, ym.start() - 2):ym.start()]
        # 跳过标准号(GB/T 7714-2015)、专利号(CN2023...)里的年份
        if re.search(r"[A-Z]{1,3}[-/]?$", prefix) and re.match(r"^\d", body[ym.end():ym.end() + 1] or ""):
            continue
        if re.search(r"(GB|CN|ISO)\s*[/·]?\s*$", body[:ym.start()]):
            continue
        d["year"] = y
        break

    # 页码："100-110"（前有冒号或逗号加分隔）
    m = re.search(r"[:：,，]\s*(\d+)\s*[-~–]\s*(\d+)(?=\s|$|\.)", body)
    if not m:
        m = re.search(r"(\d+)\s*[-~–]\s*(\d+)\s*(?:页|$)", body)
    if m:
        d["pages"] = f"{m.group(1)}-{m.group(2)}"

    # 卷(期)："46(5)" 或 "590(7845)"
    m = re.search(r"(\d+)\s*\((\d+)\)", body)
    if m:
        d["volume"], d["issue"] = m.group(1), m.group(2)

    # ---- 骨架切分：作者段 . 标题段 . 来源段 ----
    # 先从正文剥离年份/卷期/页码/序号（避免被当成段内容）
    residual = body
    residual = re.sub(r"^\[?\d+\]?\s*", "", residual)  # 行首序号（含无括号"6]"）
    if d["volume"] and d["issue"]:
        residual = residual.replace(f"{d['volume']}({d['issue']})", " ")
    if d["pages"]:
        residual = re.sub(r"[:：,，]?\s*" + re.escape(d["pages"]).replace("\\-", "[-~–]"), " ", residual)
    if d["year"]:
        residual = re.sub(r"[,，]?\s*" + d["year"] + r"\s*", " ", residual, count=1)

    # 切分策略（关键）：中文排版句点后无空格，西文有空格——两种都支持。
    # 标记位：句点 +（可选空格）+ 下一句以"内容"开始。为避免把"等."的句点误切，
    # 仅当句点后是"非数字开头"且整段长度>20 时切。
    def _split_skeleton(s):
        # 保护 URL 内的点（先替换占位）
        s2 = s
        if d["url"]:
            s2 = s2.replace(d["url"], "«URL»")
        # 按句点切（句点后跟任意非空白或空白均可），但排除小数点（数字.数字）
        pieces = re.split(r"\.(?!\d)(?=[^.\d]|$)", s2)
        pieces = [p.strip() for p in pieces if p.strip()]
        # 还原 URL
        pieces = [p.replace("«URL»", d["url"]) if d["url"] else p for p in pieces]
        return pieces

    segs = _split_skeleton(residual)
    segs = [s for s in segs if s not in ("", ".")]

    def _strip_known(seg):
        """从段中剥离已知字段痕迹，剩余部分供后续识别。"""
        s = seg
        if d["doi"]:
            s = s.replace(d["doi"], " ")
        if d["url"]:
            s = s.replace(d["url"], " ")
        s = re.sub(r"\((\d{4}-\d{2}-\d{2})\)", " ", s)
        s = re.sub(r"\[(\d{4}-\d{2}-\d{2})\]", " ", s)
        return re.sub(r"\s+", " ", s).strip(" ,.")

    if len(segs) >= 2:
        # 作者段：首段。判定：像人名序列（含逗号/顿号/and，或短中文/西文名）
        author_seg = _strip_known(segs[0])
        looks_like_authors = ("," in author_seg or "、".encode() and False or
                              " and " in author_seg.lower()
                              or re.match(r"^[A-Z][a-zA-Z\s]+$", author_seg) is not None
                              or re.match(r"^[\u4e00-\u9fa5]{2,4}$", author_seg) is not None
                              or re.match(r"^[\u4e00-\u9fa5]{2,4}(,[\u4e00-\u9fa5]{2,4})+$", author_seg) is not None)
        if looks_like_authors:
            d["authors"] = _split_authors(author_seg)
        # 标题段：第二段（含类型标识则剥离尾标）
        title_idx = 1 if d["authors"] else 0
        title_seg = segs[title_idx] if len(segs) > title_idx else ""
        tm = re.search(r"\[([A-Z]{1,2}(?:/OL)?)\]\s*$", title_seg)
        if tm:
            if not d["type_mark"]:
                d["type_mark"] = tm.group(1)
            title_seg = re.sub(r"\s*\[([A-Z]{1,2}(?:/OL)?)\]\s*$", "", title_seg)
        d["title"] = _strip_known(title_seg)
        # 来源段：作者存在时取第三段
        src_idx = 2 if d["authors"] else 1
        if len(segs) > src_idx:
            src_seg = segs[src_idx]
            sm = re.search(r"\[([A-Z]{1,2}(?:/OL)?)\]\s*$", src_seg)
            if sm:
                if not d["type_mark"]:
                    d["type_mark"] = sm.group(1)
                src_seg = re.sub(r"\s*\[[A-Z]{1,2}(?:/OL)?\]\s*$", "", src_seg)
            d["source"] = _strip_known(src_seg)
    elif len(segs) == 1:
        # 无句点分隔（手打混乱）：按第一个逗号切作者与标题
        parts = [p.strip() for p in segs[0].split(",", 1)]
        if len(parts) == 2:
            d["authors"] = _split_authors(parts[0])
            d["title"] = _strip_known(parts[1])
        else:
            d["title"] = _strip_known(segs[0])

    # 来源段细化：出版地与出版社（"北京: 清华大学出版社"）
    if d["source"]:
        pm = re.match(r"([\u4e00-\u9fa5A-Za-z ]+?)\s*:\s*(.+)", d["source"])
        if pm and re.search(r"(出版社|Press|Publishing|University)", pm.group(2)):
            d["city"] = pm.group(1).strip()
            d["publisher"] = pm.group(2).strip()
            d["source"] = None

    # 会议析出修正（v1.6）：标题段内嵌"[C]//论文集名"——题名在 "//" 前，
    # 论文集名进 source；原来源段若为"出版地: 主办方"形态，保留为出版项
    cm = re.search(r"^(.*?)\s*(?:\[([A-Z]{1,2}(?:/OL)?)?\])?\s*//\s*(.+)$", d["title"] or "")
    if cm and cm.group(1) and cm.group(1).strip():
        old_src = d.get("source")
        if old_src and re.match(r"^[^:：.]{2,20}[:：]\s*\S+$", old_src):
            m_cp = re.match(r"^([^:：]+)[:：]\s*(.+)$", old_src)
            if m_cp:
                d["city"] = m_cp.group(1).strip(" ,.")
                d["publisher"] = m_cp.group(2).strip(" ,.")
        if not d["type_mark"] and cm.group(2):
            d["type_mark"] = cm.group(2)
        d["title"] = _strip_known(cm.group(1))
        d["source"] = _strip_known(cm.group(3))

    # 来源可能粘在标题尾（"中文信息学报 2020 34(8) 1-15"被整段塞进标题）
    if d["title"] and d["source"] is None and d["volume"]:
        m3 = re.match(r"^(.*?)\s+([\u4e00-\u9fa5]{2,12}|[A-Z][A-Za-z ]{2,30})\s*$", d["title"])
        if m3:
            d["title"] = m3.group(1).strip(" ,.")
            d["source"] = m3.group(2).strip()
    return d


# ---------------------------------------------------------------------------
# ② 类型判定（特征规则 + 置信度）
# ---------------------------------------------------------------------------

def _detect_type(d):
    """类型判定：已有标识采信；否则按特征规则推断。返回 (标识, 类型名, 置信度, 依据)。"""
    if d["type_mark"]:
        name = TYPE_MARKS.get(d["type_mark"], "其他")
        return d["type_mark"], name, "高", "原文带类型标识"

    if re.search(r"(大学|学院|University|Institute)", d.get("source") or "") \
            or re.search(r"(博士|硕士学位论文|硕士论文|dissertation|thesis)",
                         d["normalized"], re.IGNORECASE):
        return "D", "学位论文", "高", "来源含学校/学位论文字样"
    if d.get("publisher") or re.search(r"(出版社|Press|Publishing)", d["normalized"]):
        return "M", "专著", "中", "含出版社字样"
    if d.get("volume") and d.get("pages"):
        return "J", "期刊论文", "高", "有卷号与页码"
    if d.get("volume") and d.get("year"):
        return "J", "期刊论文", "中", "有卷号与年份"
    if d.get("url"):
        return "EB/OL", "电子资源", "中", "有 URL 无卷期"
    if d.get("source") and d.get("year") and d.get("title"):
        return "J", "期刊论文", "低", "有来源/年份/标题但缺卷期（按期刊推断，请复核）"
    return None, "未知", "低", "字段不足，无法判定（请人工补全）"


# ---------------------------------------------------------------------------
# ③ 国标重排
# ---------------------------------------------------------------------------

def _fmt_authors_gbt(authors, western, max_authors=3):
    """作者列表国标化：>max 位截断加 等/et al.；中文全名、西文姓前名缩写。"""
    if not authors:
        return ""
    fmt = _fmt_western_author if western else _fmt_chinese_author
    formatted = [fmt(a) for a in authors]
    if len(formatted) > max_authors:
        tail = "et al" if western else "等"
        return ", ".join(formatted[:max_authors]) + ", " + tail
    return ", ".join(formatted)


def _fmt_pages_gbt(pages):
    if not pages:
        return ""
    return pages.replace("~", "-").replace("–", "-")


def render_gbt(d, index=None, style="numeric"):
    """渲染单条国标引文。style: numeric（[1] 前缀）/ author_year（作者-年份制）。

    字段拼接只用解析出的结构化字段（不回贴原文段落），彻底避免重复。"""
    western = _is_western(d["normalized"])
    authors = _fmt_authors_gbt(d["authors"], western)
    type_mark, type_name, conf, _ = _detect_type(d)

    def _seg(s):
        return s.strip(" ,.") if s else ""

    # 作者段
    author_part = authors
    # 标题段（附类型标识）
    title_part = _seg(d["title"])
    if title_part and type_mark:
        title_part = f"{title_part}[{type_mark}]"
    # 出版项：专著/学位论文 → "出版地: 出版社, 年份"；期刊 → "来源, 年, 卷(期): 页"
    parts = []
    if style == "numeric" and index is not None:
        parts.append(f"[{index}]")
    if author_part:
        parts.append(author_part)
    # 会议析出：题名[C]//论文集名 —— source 并入标题段（v1.6），后续分支不再重复输出
    source_in_title = False
    if title_part:
        if type_mark == "C" and d.get("source"):
            parts.append(f"{title_part}//{_seg(d['source'])}")
            source_in_title = True
        else:
            parts.append(title_part)

    if d.get("publisher") or d.get("city"):
        pub = []
        if d.get("city"):
            pub.append(d["city"])
        if d.get("publisher"):
            pub.append(d["publisher"])
        pub_str = ": ".join(pub)
        if d["year"]:
            pub_str += f", {d['year']}"
        if d["pages"] and type_mark in ("M", "D", "C"):
            pub_str += f": {d['pages']}"
        parts.append(pub_str)
        if d.get("source") and not source_in_title and d["publisher"] and d["source"] != d["publisher"]:
            parts.append(d["source"])
    else:
        src = d.get("source") if not source_in_title else None
        if src:
            tail = src
            if d["year"]:
                tail += f", {d['year']}"
            if d["volume"]:
                tail += f", {d['volume']}" + (f"({d['issue']})" if d["issue"] else "")
            if d["pages"]:
                tail += f": {d['pages']}"
            parts.append(tail)
        else:
            if d["year"]:
                parts.append(d["year"])
            if d["volume"]:
                parts.append(d["volume"] + (f"({d['issue']})" if d["issue"] else ""))
            if d["pages"]:
                parts.append(d["pages"])

    if d["doi"]:
        parts.append(f"DOI: {d['doi']}")
    elif d["url"]:
        url_part = d["url"]
        if d.get("access_date"):
            url_part += f" [{d['access_date']}]"
        elif d.get("pub_date"):
            url_part = f"({d['pub_date']})[{d.get('access_date') or '引用日期待补'}] {url_part}"
        parts.append(url_part)

    line = ". ".join(p for p in parts if p)
    if style == "author_year":
        first_author = d["authors"][0] if d["authors"] else "佚名"
        fa = (_fmt_western_author(first_author) if western else first_author)
        yr = d["year"] or "n.d."
        body = ". ".join(p for p in parts[1:] if p) if len(parts) > 1 else ""
        line = f"{fa}, {yr}. {body}".rstrip(" .") + "."
    else:
        line = line.rstrip(" .") + "."
    return line, {"type_mark": type_mark, "type_name": type_name, "confidence": conf}


# ---------------------------------------------------------------------------
# ④ 主流程：批量处理 + 对照表 + 质量报告
# ---------------------------------------------------------------------------

def _looks_like_new_entry(s):
    """断行续写判定：行首特征是否为"新条目起点"。

    三类可靠特征（v1.6 增强，修复"不带序号的独立条目被误并入前一条"）：
    1. [n] 序号或数字开头（保持 v1.4 原行为，兼容 "1." 式编号）；
    2. 西文作者段：全大写姓氏 + 缩写名开头，如 "LECUN Y," / "SMITH J K."；
    3. 中文作者段：2-4 汉字姓名 + 逗号/顿号，如 "王建国, "。
    其余行（小写开头、"Nature, ..."、出版地开头等）视为前一条的续行。
    """
    if re.match(r"^\[?\d+\]?", s):
        return True
    if re.match(r"^[A-Z][A-Z\-']+(\s+[A-Z]\.?)+[\s,，\.]", s):
        return True
    if re.match(r"^[\u4e00-\u9fff]{2,4}\s*[,，、]", s):
        return True
    return False


def read_citations(path):
    """读入引文：txt（每行一条，空行忽略；# 开头注释忽略）/ 直接传引文列表。

    断行续写：一条引文折行时，非条目起点的行自动并入前一条。
    难以判定时建议每行开头加 [n] 序号（最可靠）。
    """
    if isinstance(path, (list, tuple)):
        return [t.strip() for t in path if t.strip()]
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    items, buf = [], ""
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if buf == "" or _looks_like_new_entry(s):
            if buf:
                items.append(buf)
            buf = s
        else:
            buf = buf + " " + s
    if buf:
        items.append(buf)
    return items


def _parse_quality_flag(d):
    """解析质量检查：字段残缺/可疑时返回提醒文本（不影响类型置信度，仅提示复核）。

    诚信机制：宁可多提醒、不可漏提醒。
    """
    flags = []
    t = d.get("title") or ""
    if t and re.search(r"(GB/T|GB |ISO|CN\d)", t):
        flags.append("疑似标准号/专利号被切分（其中年份可能被误作出版年），请核对标准号完整性")
    if d.get("type_mark") in ("EB/OL", "DB/OL") and not d.get("url"):
        flags.append("电子资源缺 URL")
    if d.get("type_mark") == "D" and d.get("source") and not re.search(r"(大学|学院|University)", d["source"]):
        flags.append("学位论文来源不含学校字样，请核对")
    if not d.get("authors") and d.get("title"):
        flags.append("作者未识别（机构名可能被误入标题位）")
    return "；".join(flags)


def format_citations(raw_list, style="numeric", sortby="order"):
    """批量格式化主入口。返回 dict：entries/对照表数据/质量报告。"""
    entries = []
    for i, raw in enumerate(raw_list, 1):
        d = _parse_citation(raw)
        line, meta = render_gbt(d, index=(i if style == "numeric" else None), style=style)
        quality_flag = _parse_quality_flag(d)
        # 类型高置信但解析存疑 → 降为中（进待复核清单）
        conf = meta["confidence"]
        if quality_flag and conf == "高":
            conf = "中"
        entries.append({"index": i, "raw": raw, "formatted": line,
                        "type_mark": meta["type_mark"], "type_name": meta["type_name"],
                        "confidence": conf, "quality_flag": quality_flag, "fields": d})

    if sortby == "author":
        entries.sort(key=lambda e: (e["fields"]["authors"][0] if e["fields"]["authors"] else "~~~"))

    low_conf = [e for e in entries if e["confidence"] != "高"]
    report = {
        "total": len(entries),
        "high_confidence": len(entries) - len(low_conf),
        "needs_review": len(low_conf),
    }
    return {"entries": entries, "report": report}


def export_outputs(result, out_dir=None, out_format="markdown", style="numeric"):
    """输出三件套：规范条目 + 对照表 + 质量报告。返回全部路径。"""
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    entries, report = result["entries"], result["report"]
    paths = {}

    # 1) 规范条目
    bib_path = out_dir / "参考文献_国标.md"
    lines = ["# 参考文献（GB/T 7714-2015 自动整理版）", "",
             "> 由 citation_formatter.py 生成；低置信条目已标注，请按对照表人工复核。", ""]
    lines += [f"{e['formatted']}" for e in entries]
    lines += ["", f"---", f"共 {report['total']} 条｜高置信 {report['high_confidence']} 条｜待人工复核 {report['needs_review']} 条"]
    bib_path.write_text("\n".join(lines), encoding="utf-8")
    paths["bib"] = bib_path

    # 2) 对照表
    if out_format == "csv":
        tbl_path = out_dir / "对照表.csv"
        import csv
        with open(tbl_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["序号", "原文", "国标格式", "类型", "置信度"])
            for e in entries:
                w.writerow([e["index"], e["raw"], e["formatted"],
                            f"{e['type_name']}", e["confidence"]])
    else:
        tbl_path = out_dir / "对照表.md"
        lines = ["# 原文-国标对照表", "",
                 "| # | 原文 | 国标格式 | 类型 | 置信度 |",
                 "|---|---|---|---|---|"]
        for e in entries:
            lines.append(f"| {e['index']} | {e['raw'][:60]}{'…' if len(e['raw']) > 60 else ''} "
                         f"| {e['formatted']} | {e['type_name']} | {e['confidence']} |")
        tbl_path.write_text("\n".join(lines), encoding="utf-8")
    paths["table"] = tbl_path

    # 3) 质量报告（待复核清单）
    if report["needs_review"]:
        rpt_path = out_dir / "待复核清单.md"
        lines = ["# 待人工复核清单", "",
                 "以下条目类型判定置信度为中/低，或字段缺失/解析存疑，请人工核对：", ""]
        for e in entries:
            if e["confidence"] != "高":
                lines.append(f"- **[{e['index']}] {e['type_name']}（置信度：{e['confidence']}）**")
                lines.append(f"  - 原文：{e['raw']}")
                lines.append(f"  - 当前输出：{e['formatted']}")
                missing = [k for k in ("authors", "year", "title", "source", "volume", "pages")
                           if not e["fields"].get(k)]
                if missing:
                    lines.append(f"  - 缺失字段：{', '.join(missing)}")
                if e.get("quality_flag"):
                    lines.append(f"  - ⚠ {e['quality_flag']}")
        rpt_path.write_text("\n".join(lines), encoding="utf-8")
        paths["review"] = rpt_path
    return paths


# ---------------------------------------------------------------------------
# 演示入口
# ---------------------------------------------------------------------------

def _demo():
    src = SAMPLES / "demo_citations_mixed.txt"
    print(f"演示数据：{src}\n")
    raw = read_citations(src)
    result = format_citations(raw, style="numeric")
    print(f"输入 {len(raw)} 条 → 解析 {result['report']['total']} 条"
          f"（高置信 {result['report']['high_confidence']}，待复核 {result['report']['needs_review']}）\n")
    for e in result["entries"]:
        flag = "" if e["confidence"] == "高" else f"  ← {e['type_name']}·{e['confidence']}置信"
        print(f"{e['formatted']}{flag}")
    paths = export_outputs(result, out_dir=DEFAULT_OUT)
    print(f"\n输出：{list(paths.values())}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="GB/T 7714 参考文献批量格式化")
    ap.add_argument("input", nargs="?", help="引文 txt 文件（每行一条）")
    ap.add_argument("--style", default="numeric", choices=["numeric", "author_year"],
                    help="标注制式（默认 numeric 顺序编码制）")
    ap.add_argument("--sortby", default="order", choices=["order", "author"],
                    help="排序（默认按输入顺序；author=按第一作者）")
    ap.add_argument("--out_format", default="markdown", choices=["markdown", "csv"],
                    help="对照表格式（默认 markdown）")
    ap.add_argument("--out", default=None, help="输出目录（默认 .temp/citations/）")
    ap.add_argument("--demo", action="store_true", help="用 samples/ 数据演示")
    args = ap.parse_args(argv)
    if args.demo:
        _demo()
    elif args.input:
        raw = read_citations(args.input)
        result = format_citations(raw, style=args.style, sortby=args.sortby)
        for e in result["entries"]:
            print(e["formatted"])
        paths = export_outputs(result, out_dir=args.out, out_format=args.out_format,
                               style=args.style)
        print(f"\n共 {result['report']['total']} 条｜待复核 {result['report']['needs_review']} 条")
        print(f"输出：{list(paths.values())}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main(sys.argv[1:])
