# -*- coding: utf-8 -*-
"""
citation_verifier.py — 引文元数据补全与真伪核验（academic-research 技能 v1.5 · 核心创新）

基于真实用户痛点调研设计（知乎/CSDN 高赞帖）：
  痛点①：知网/EndNote 导出"只有标题作者，没有DOI、卷期页码，年份都缺"，
         手动补全"耗掉整个下午"→ 元数据补全（--enrich）
  痛点②：AI 编造文献已成公害（"查无此书的参考文献，AI写得有模有样"，
         Nature 调查 60%+ 科研人员遇到过）→ 真伪核验（--verify）

数据源：Crossref API（https://api.crossref.org）——免费、无需密钥的
学术 DOI 权威元数据接口。所有核验结论均附来源链接，可追溯。

设计原则（诚信红线）：
  1. 判定边界：**未命中 ≠ 编造**——检索覆盖有限（尤其中文文献），
     未命中只输出"存疑待人工复核"，绝不下"编造"结论
  2. 元数据补全只对"命中且相似度高"的条目执行，低置信不动原字段
  3. 每次核验输出完整报告（已验证/存疑/无法核验三类 + 证据链接）

用法：
  python citation_verifier.py 引文.txt --verify              # 真伪核验
  python citation_verifier.py 引文.txt --enrich              # 元数据补全（补全后输出新格式化表）
  python citation_verifier.py 引文.txt --verify --enrich     # 核验+补全一体
  python citation_verifier.py --demo                         # 样例集自验

依赖：仅 Python 标准库（urllib/json/difflib）+ citation_formatter 本地解析。
"""

import argparse
import difflib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TOOLS_DIR.parent
SAMPLES = SKILL_ROOT / "samples"
DEFAULT_OUT = Path(".temp") / "citation_verify"

sys.path.insert(0, str(TOOLS_DIR))
from citation_formatter import (  # noqa: E402
    _parse_citation, read_citations, render_gbt, format_citations,
    export_outputs, _is_western,
)

UA = {"User-Agent": "academic-research-skill/1.0 (mailto:team@example.com)"}
TIMEOUT = 20
SIM_THRESHOLD = 0.85   # 标题相似度阈值：≥0.85 判命中
FIELDS_SELECT = "DOI,title,author,issued,container-title,volume,issue,page,type"


# ---------------------------------------------------------------------------
# Crossref API 封装（含限速礼貌：Crossref 要求间隔 ~1s 或带 contact 邮箱）
# ---------------------------------------------------------------------------

def _http_get_json(url, retries=2):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if attempt == retries:
                print(f"  [网络失败] {url[:80]}… : {e}")
                return None
            time.sleep(1.5)


def cr_works_by_doi(doi):
    """DOI 直查 → 权威元数据 dict（100% 可靠）。"""
    data = _http_get_json(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}")
    return data["message"] if data else None


def cr_search_by_title(title, author=None, rows=5, container=None):
    """标题（+作者+容器）检索 → 候选列表。用于无 DOI 条目的匹配与核验。"""
    q = urllib.parse.quote(title)
    url = (f"https://api.crossref.org/works?query.bibliographic={q}"
           f"&rows={rows}&select={FIELDS_SELECT}")
    if author:
        url += f"&query.author={urllib.parse.quote(author)}"
    if container:
        url += f"&query.container-title={urllib.parse.quote(container)}"
    data = _http_get_json(url)
    return data["message"]["items"] if data else []


def _title_sim(a, b):
    return difflib.SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def _cr_to_fields(msg):
    """Crossref 元数据 → 标准字段 dict。"""
    year = None
    try:
        year = msg["issued"]["date-parts"][0][0]
    except (KeyError, IndexError, TypeError):
        pass
    authors = []
    for a in msg.get("author", []) or []:
        family = a.get("family", "")
        given = a.get("given", "")
        authors.append(f"{family} {given}".strip())
    return {
        "doi": msg.get("DOI"),
        "title": (msg.get("title") or [""])[0],
        "source": (msg.get("container-title") or [""])[0] or None,
        "year": str(year) if year else None,
        "volume": msg.get("volume"),
        "issue": msg.get("issue"),
        "pages": msg.get("page"),
        "authors": authors,
        "type": msg.get("type"),
        "url": f"https://doi.org/{msg.get('DOI')}" if msg.get("DOI") else None,
    }


# ---------------------------------------------------------------------------
# 核验与补全主逻辑
# ---------------------------------------------------------------------------

def verify_entry(parsed, sim_threshold=SIM_THRESHOLD):
    """单条核验：DOI 直查（权威）→ 标题+作者+来源检索（匹配）→ 判定。

    返回 dict：status ∈ {verified, matched, unverified, unverifiable}，附证据。
    - verified ：DOI 直查命中（权威元数据）
    - matched  ：标题相似度 ≥ 阈值（高置信匹配；短标题时叠加期刊名/作者双重验证）
    - unverified：检索未命中（存疑待人工复核，**不判编造**）
    - unverifiable：无标题/无网络，无法核验
    """
    title = parsed.get("title")
    if not title or len(title) < 6:
        return {"status": "unverifiable", "reason": "无有效标题，无法核验", "evidence": None}
    if parsed.get("doi"):
        msg = cr_works_by_doi(parsed["doi"])
        if msg:
            fields = _cr_to_fields(msg)
            sim = _title_sim(title, fields["title"])
            if sim >= 0.5:  # DOI 命中即权威，标题近似即可（存在副标题差异）
                return {"status": "verified", "reason": f"DOI 直查命中（Crossref 权威元数据，标题相似度 {sim:.2f}）",
                        "evidence": fields}
        # DOI 查不到（可能 DOI 本身有误）→ 落回标题检索
    first_author = parsed["authors"][0] if parsed.get("authors") else None
    # 西文作者取姓氏部分（Crossref query.author 姓氏效果最好）
    if first_author and _is_western(first_author):
        tokens = re.split(r"[, ]", first_author)
        first_author = tokens[0] if tokens else None
    # 短标题（泛化词多）时叠加期刊名过滤，避免同名词误配
    short_title = len(title) < 25
    items = cr_search_by_title(title, author=first_author,
                              container=parsed.get("source") if short_title else None)
    if not items and short_title and parsed.get("source"):
        items = cr_search_by_title(title, author=first_author)  # 容器过滤无结果时放宽
    if not items:
        return {"status": "unverifiable", "reason": "网络检索无返回", "evidence": None}
    best, best_sim, best_fields = None, 0.0, None
    for it in items:
        t = (it.get("title") or [""])[0]
        sim = _title_sim(title, t)
        # 综合评分：标题相似度为主，来源一致加成（解决短标题同名词问题）
        src_bonus = 0.0
        if parsed.get("source") and it.get("container-title"):
            if parsed["source"].lower() in (it["container-title"][0] or "").lower() or \
               (it["container-title"][0] or "").lower() in parsed["source"].lower():
                src_bonus = 0.15
        score = min(sim + src_bonus, 1.0)  # 封顶 1.0（加成为辅助证据，不超出完全匹配）
        if score > best_sim:
            best, best_sim, best_fields = it, score, _cr_to_fields(it)
    if best_sim >= sim_threshold:
        return {"status": "matched",
                "reason": f"标题检索高置信匹配（相似度 {best_sim:.2f} ≥ {sim_threshold}）",
                "evidence": best_fields}
    return {"status": "unverified",
            "reason": f"未检索到匹配文献（最高相似度 {best_sim:.2f} < {sim_threshold}）；"
                      f"注意：检索覆盖有限（尤其中文文献），未命中≠编造，请人工复核",
            "evidence": best_fields if best_sim > 0.6 else None}


def enrich_entry(parsed, evidence, sim_threshold=0.5):
    """用 Crossref 权威元数据补全缺失字段（只补缺失，不覆盖已有）。"""
    if not evidence:
        return parsed, []
    filled = []
    field_map = {
        "doi": ("doi", "DOI"), "title": ("title", "标题"), "source": ("source", "来源"),
        "year": ("year", "年份"), "volume": ("volume", "卷"), "issue": ("issue", "期"),
        "pages": ("pages", "页码"),
    }
    for key, (ev_key, zh) in field_map.items():
        ev_val = evidence.get(ev_key)
        if ev_val and not parsed.get(key):
            parsed[key] = str(ev_val) if not isinstance(ev_val, str) else ev_val
            filled.append(zh)
    # 作者缺失且差异大时补全（保守：只在完全无作者时）
    if not parsed.get("authors") and evidence.get("authors"):
        parsed["authors"] = evidence["authors"]
        filled.append("作者")
    return parsed, filled


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

STATUS_ZH = {"verified": "✓ 已验证", "matched": "✓ 高置信匹配",
             "unverified": "⚠ 存疑待复核", "unverifiable": "— 无法核验"}


def run_verify(raw_list, do_verify=True, do_enrich=False, out_dir=None,
               sim_threshold=SIM_THRESHOLD):
    """批量核验/补全主入口。返回结构化结果。"""
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    print(f"开始处理 {len(raw_list)} 条引文（核验={do_verify}，补全={do_enrich}）")
    print(f"数据源：Crossref（学术 DOI 权威元数据，免费公开接口）\n")

    for i, raw in enumerate(raw_list, 1):
        parsed = _parse_citation(raw)
        entry = {"index": i, "raw": raw, "parsed": parsed,
                 "status": None, "reason": "", "evidence": None, "filled": []}
        if do_verify:
            v = verify_entry(parsed, sim_threshold)
            entry["status"], entry["reason"], entry["evidence"] = \
                v["status"], v["reason"], v["evidence"]
            if do_enrich and v["status"] in ("verified", "matched"):
                parsed, filled = enrich_entry(parsed, v["evidence"])
                entry["filled"] = filled
            # 补全后重新渲染该条
            line, meta = render_gbt(parsed, index=i, style="numeric")
            entry["formatted"] = line
            entry["type_name"] = meta["type_name"]
        else:
            line, meta = render_gbt(parsed, index=i, style="numeric")
            entry["formatted"] = line
            entry["type_name"] = meta["type_name"]
        results.append(entry)
        mark = STATUS_ZH.get(entry["status"], "")
        fill_note = f"｜补全: {'/'.join(entry['filled'])}" if entry["filled"] else ""
        print(f"  [{i}] {mark}{fill_note} {str(entry['parsed'].get('title') or entry['raw'])[:40]}")
        time.sleep(1.0)  # Crossref 礼貌限速
    return results


def export_verify_report(results, out_dir, enriched_table=None):
    """输出核验报告（+可选补全后的新文献表）。"""
    out_dir = Path(out_dir)
    lines = ["# 引文核验报告", "",
             f"- 核验时间：{time.strftime('%Y-%m-%d %H:%M')}",
             "- 数据源：Crossref（https://api.crossref.org，学术 DOI 权威元数据）",
             "- 判定边界：**未命中 ≠ 编造**——检索覆盖有限（尤其中文文献），"
             "未命中仅表示存疑待人工复核", ""]
    stat = {"verified": 0, "matched": 0, "unverified": 0, "unverifiable": 0}
    for e in results:
        if e["status"]:
            stat[e["status"]] = stat.get(e["status"], 0) + 1
    lines.append(f"## 总览：已验证 {stat['verified']}｜高置信匹配 {stat['matched']}｜"
                 f"存疑待复核 {stat['unverified']}｜无法核验 {stat['unverifiable']}（共 {len(results)} 条）")
    lines.append("")
    for e in results:
        if not e["status"]:
            continue
        lines.append(f"### [{e['index']}] {STATUS_ZH[e['status']]}")
        lines.append(f"- 原文：{e['raw']}")
        if e["formatted"] != e["raw"]:
            lines.append(f"- 规范化：{e['formatted']}")
        lines.append(f"- 判定依据：{e['reason']}")
        ev = e.get("evidence")
        if ev:
            lines.append(f"- 来源：{ev.get('title', '')}")
            if ev.get("url"):
                lines.append(f"- 链接：{ev['url']}")
        if e["filled"]:
            lines.append(f"- 已补全字段：{', '.join(e['filled'])}")
        lines.append("")
    lines.append("## 使用说明")
    lines.append("")
    lines.append("- `✓ 已验证`：DOI 直查命中 Crossref 权威元数据，文献真实存在；")
    lines.append("- `✓ 高置信匹配`：标题检索高相似度匹配，强烈建议点开链接人工确认；")
    lines.append("- `⚠ 存疑待复核`：**不代表编造**（中文文献 Crossref 覆盖有限），请通过知网/谷歌学术人工检索确认；")
    lines.append("- 最终判断权归作者；本工具只提供可追溯的核验证据，不替代人工核查。")
    report_path = out_dir / "引文核验报告.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    paths = {"report": report_path}
    if enriched_table is not None:
        tbl_path = out_dir / "补全后文献表.md"
        tbl_path.write_text("\n".join(["# 补全后参考文献表（GB/T 7714）", ""] + enriched_table),
                            encoding="utf-8")
        paths["enriched"] = tbl_path
    return paths


# ---------------------------------------------------------------------------
# 演示与命令行入口
# ---------------------------------------------------------------------------

def _demo():
    src = SAMPLES / "demo_citations_mixed.txt"
    print(f"演示数据：{src}（核验前 3 条西文条目演示，全量请直接传文件）\n")
    raw = read_citations(src)[:5]  # 演示前5条（含2条西文期刊）控制时长
    results = run_verify(raw, do_verify=True, do_enrich=True,
                         out_dir=DEFAULT_OUT)
    paths = export_verify_report(results, DEFAULT_OUT)
    print(f"\n输出：{list(paths.values())}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="引文元数据补全与真伪核验（Crossref）")
    ap.add_argument("input", nargs="?", help="引文 txt 文件（每行一条）")
    ap.add_argument("--verify", action="store_true", help="执行真伪核验")
    ap.add_argument("--enrich", action="store_true", help="补全缺失字段（需检索命中）")
    ap.add_argument("--out", default=None, help="输出目录（默认 .temp/citation_verify/）")
    ap.add_argument("--sim", type=float, default=SIM_THRESHOLD,
                    help=f"标题匹配相似度阈值（默认 {SIM_THRESHOLD}）")
    ap.add_argument("--demo", action="store_true", help="样例集演示（前5条）")
    args = ap.parse_args(argv)
    if args.demo:
        _demo()
    elif args.input and (args.verify or args.enrich):
        raw = read_citations(args.input)
        results = run_verify(raw, do_verify=args.verify, do_enrich=args.enrich,
                             out_dir=args.out, sim_threshold=args.sim)
        # 补全模式下额外导出补全后的完整文献表
        enriched = None
        if args.enrich:
            enriched = [e["formatted"] for e in results]
        paths = export_verify_report(results, Path(args.out) if args.out else DEFAULT_OUT,
                                     enriched_table=enriched)
        print(f"\n输出：{list(paths.values())}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main(sys.argv[1:])
