#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纠错诊断质量测试（方法①）——绕过 agent 与图库，直接把「纠错输入」喂给模型，只测诊断。

为什么单独测诊断：纠错环节由提示词驱动（代码里没有实现），整条闭环依赖 LLM 行为；
把它拆出来单独喂输入，才能得到**可重复、可量化**的结果——改提示词前后各跑一遍就知道有没有变好。

注意：nl2sql-correction/SKILL.md 里自带 3 个纠错示范（括号未闭合 / JOIN 用错列 / HAVING 误用），
那 3 条的答案等于写在卷子上。下面的用例**全部是另造的**，且覆盖分类法 9 大类。

只用标准库，不需要项目 venv。

用法：
    python scripts/test_correction.py --dry-run            # 只拼提示词，不调 API
    python scripts/test_correction.py                      # 跑全部用例
    python scripts/test_correction.py --only A_col_missing,J_order_limit_missing
    python scripts/test_correction.py --json result.json   # 结果另存
    python scripts/test_correction.py --show               # 打印模型原始回答

配置读仓库根 .env 的 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL，环境变量可覆盖。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO / "backend/src/app/skills/nl2sql/nl2sql-correction"
SKILL_MD = SKILL_DIR / "SKILL.md"
TAXONOMY_MD = SKILL_DIR / "references/error-taxonomy.md"
ENV_FILE = REPO / ".env"

# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #


def load_dotenv(path: Path) -> dict[str, str]:
    """极简 .env 解析：KEY=VALUE，跳过注释与空行，去掉引号和行尾 \\r。"""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        val = val.strip().strip('"').strip("'")
        out[key] = val
    return out


# --------------------------------------------------------------------------- #
# 测试用例：12 条，覆盖分类法 9 大类；每条都给出「我认定的正确答案」
# expected_categories 第一项 = 主根因所在大类
# --------------------------------------------------------------------------- #

SCHEMA_TRACKS = """tracks(TrackId PK, Name, AlbumId FK->albums.AlbumId,
        MediaTypeId FK->media_types.MediaTypeId, GenreId FK->genres.GenreId,
        Composer, Milliseconds, UnitPrice)
albums(AlbumId PK, Title, ArtistId FK->artists.ArtistId)
artists(ArtistId PK, Name)
genres(GenreId PK, Name)
media_types(MediaTypeId PK, Name)"""

SCHEMA_INVOICE = """customers(CustomerId PK, FirstName, LastName, Country, SupportRepId FK->employees.EmployeeId)
invoices(InvoiceId PK, CustomerId FK->customers.CustomerId, InvoiceDate, Total)
invoice_items(InvoiceLineId PK, InvoiceId FK->invoices.InvoiceId,
        TrackId FK->tracks.TrackId, UnitPrice, Quantity)"""

CASES: list[dict] = [
    dict(
        id="A_col_missing",
        question="列出曲目名称和它们所属的媒体类型编号",
        schema=SCHEMA_TRACKS,
        failed_sql="SELECT t.Name, t.MediaType FROM tracks t LIMIT 10",
        error="no such column: t.MediaType",
        expected_categories=["schema_link"],
        expected_codes=["schema_link.col_missing"],
    ),
    dict(
        id="B_table_missing",
        question="统计摇滚（Rock）这个音乐类型下的曲目数量",
        schema=SCHEMA_TRACKS,
        failed_sql="SELECT COUNT(*) FROM genre WHERE Name = 'Rock'",
        error="no such table: genre",
        expected_categories=["schema_link"],
        expected_codes=["schema_link.table_missing"],
    ),
    dict(
        id="C_join_missing",
        question="列出每张专辑的标题和它的艺术家名字",
        schema=SCHEMA_TRACKS,
        failed_sql="SELECT a.Title, ar.Name FROM albums a, artists ar LIMIT 20",
        error="执行成功但结果明显不对：行数远多于专辑数量，两个表之间没有任何关联条件",
        expected_categories=["join"],
        expected_codes=["join.join_missing"],
    ),
    dict(
        id="D_join_wrong_type",
        question="列出每位客户及其发票数量，没有任何发票的客户也要列出来（数量显示 0）",
        schema=SCHEMA_INVOICE,
        failed_sql=(
            "SELECT c.FirstName, c.LastName, COUNT(i.InvoiceId) AS cnt "
            "FROM customers c JOIN invoices i ON c.CustomerId = i.CustomerId "
            "GROUP BY c.CustomerId"
        ),
        error="执行成功但结果不全：没有任何发票的客户没有出现在结果里",
        expected_categories=["join"],
        expected_codes=["join.join_wrong_type"],
    ),
    dict(
        id="E_where_missing",
        question="统计 2010 年 1 月 1 日之后开出的发票数量",
        schema=SCHEMA_INVOICE,
        failed_sql="SELECT COUNT(*) FROM invoices",
        error="执行成功但与问题不符：返回了全部发票的总数，完全没有按日期过滤",
        expected_categories=["filter"],
        expected_codes=["filter.where_missing"],
    ),
    dict(
        id="F_groupby_missing_col",
        question="统计每个国家的发票总额",
        schema=SCHEMA_INVOICE,
        failed_sql=(
            "SELECT c.Country, c.LastName, SUM(i.Total) AS total "
            "FROM customers c JOIN invoices i ON c.CustomerId = i.CustomerId "
            "GROUP BY c.Country"
        ),
        error="执行成功但结果不可用：LastName 既不在 GROUP BY 中也不是聚合列，SQLite 随机取组内某一行",
        expected_categories=["aggregation"],
        expected_codes=["aggregation.groupby_missing_col"],
    ),
    dict(
        id="G_hardcoded_value",
        question="找出销售额最高的那个月是哪个月",
        schema=SCHEMA_INVOICE,
        failed_sql=(
            "SELECT strftime('%Y-%m', InvoiceDate) AS m, SUM(Total) AS s "
            "FROM invoices WHERE strftime('%Y-%m', InvoiceDate) = '2010-01' GROUP BY m"
        ),
        error="执行成功但答非所问：某个月份被写死在 WHERE 里，并没有去比较各个月份的销售额",
        expected_categories=["value"],
        expected_codes=["value.hardcoded_value"],
    ),
    dict(
        id="H_subquery_missing",
        question="找出消费总额高于其所在国家平均消费额的客户",
        schema=SCHEMA_INVOICE,
        failed_sql=(
            "SELECT c.FirstName, SUM(i.Total) AS total "
            "FROM customers c JOIN invoices i ON c.CustomerId = i.CustomerId "
            "GROUP BY c.CustomerId ORDER BY total DESC"
        ),
        error="执行成功但缺少比较基准：只按消费额排序，没有计算各国平均消费额，也没有做过滤",
        expected_categories=["subquery"],
        expected_codes=["subquery.subquery_missing"],
    ),
    dict(
        id="I_except_missing",
        question="列出不包含任何曲目的播放列表",
        schema="playlists(PlaylistId PK, Name)\nplaylist_track(PlaylistId FK->playlists.PlaylistId, TrackId FK->tracks.TrackId)",
        failed_sql=(
            "SELECT p.Name FROM playlists p "
            "JOIN playlist_track pt ON p.PlaylistId = pt.PlaylistId"
        ),
        error="执行成功但语义相反：返回的是「含有曲目」的播放列表，没有做「不包含」判断",
        expected_categories=["set_ops"],
        expected_codes=["set_ops.except_missing"],
    ),
    dict(
        id="J_order_limit_missing",
        question="销售额最高的前 5 个音乐类型",
        schema=SCHEMA_INVOICE + "\n" + SCHEMA_TRACKS,
        failed_sql=(
            "SELECT g.Name, SUM(ii.UnitPrice * ii.Quantity) AS amount "
            "FROM genres g JOIN tracks t ON g.GenreId = t.GenreId "
            "JOIN invoice_items ii ON t.TrackId = ii.TrackId GROUP BY g.Name"
        ),
        error="执行成功但没有排序也没有数量限制：返回了全部类型，且顺序未定义，问题要的是前 5",
        expected_categories=["other"],
        expected_codes=["other.order_by_missing", "other.limit_missing"],
    ),
    dict(
        id="K_syntax_keyword_typo",
        question="查询专辑 1 里的曲目名称",
        schema=SCHEMA_TRACKS,
        failed_sql="SELECT Name FROM tracks WHER AlbumId = 1",
        error='near "WHER": syntax error',
        expected_categories=["syntax"],
        expected_codes=["syntax.sql_syntax_error"],
    ),
    dict(
        id="L_ambiguous_col",
        question="查询标题为某个值的专辑里曲目的名称",
        schema=SCHEMA_TRACKS,
        failed_sql=(
            "SELECT Name FROM tracks t JOIN albums a ON t.AlbumId = a.AlbumId "
            "WHERE Name = 'For Those About To Rock'"
        ),
        error="ambiguous column name: Name",
        expected_categories=["schema_link"],
        expected_codes=["schema_link.ambiguous_col"],
    ),
]

# 有些"多报"其实是模型的合理补充（同一故障的次生表现），不该算错。
# 列在这里的额外编码不计入"无理多报"。
ALLOWED_EXTRA: dict[str, set[str]] = {
    "B_table_missing": {"join.join_missing"},              # 表名错，但后续确实需要 join
    "F_groupby_missing_col": {"other.extra_values_selected"},  # 多选列正是 extra_values_selected 的定义
    "G_hardcoded_value": {"other.order_by_missing", "other.limit_missing"},  # "取最高" 等价于排序+取一
    "H_subquery_missing": {"filter.where_missing",          # 缺比较基准，也可表述为缺过滤
                           "aggregation.groupby_missing_col"},  # 该 SQL 里 FirstName 也确实没进 GROUP BY，属第二个真实缺陷
    "L_ambiguous_col": {"filter.condition_wrong_col"},     # WHERE 该针对专辑标题，属额外合理观察
}

OUTPUT_CONTRACT = """
---
# 本次任务：只做「诊断」，不要输出修正后的 SQL

请以 Correction Plan Agent（Part A）的身份，针对下面这条失败的查询，按错误分类法定位根因，
**仅输出一个 JSON 对象**（不要 markdown 围栏、不要 JSON 以外的任何文字）：

{
  "error_codes": ["<category.subcategory>", "..."],
  "root_cause": "<一句话说明最根本的失败原因>",
  "cot_reasoning": "<简要诊断推理>",
  "repair_strategy": ["<修复动作 1>", "<修复动作 2>"]
}

要求：
- `error_codes` 使用分类法的**完整编码**（如 `aggregation.agg_no_groupby`），**主根因排在第一**；
- 只列真正适用的编码，不要罗列所有可能项；
- 编码必须来自给定分类法，不要自造。
"""


def build_system_prompt() -> str:
    skill = SKILL_MD.read_text(encoding="utf-8")
    taxonomy = TAXONOMY_MD.read_text(encoding="utf-8")
    return (
        f"{skill}\n\n"
        f"---\n\n# 错误分类法全文（唯一权威编码来源）\n\n{taxonomy}\n"
        f"{OUTPUT_CONTRACT}"
    )


def build_user_prompt(case: dict) -> str:
    return (
        f"## 原始自然语言问题\n{case['question']}\n\n"
        f"## 精简 Schema（可从 FalkorDB 检索得到）\n{case['schema']}\n\n"
        f"## 失败的 SQL\n```sql\n{case['failed_sql']}\n```\n\n"
        f"## 执行反馈\n{case['error']}\n"
    )


# --------------------------------------------------------------------------- #
# 调用模型
# --------------------------------------------------------------------------- #


def call_model(cfg: dict, system_prompt: str, user_prompt: str, timeout: int) -> tuple[str, float]:
    payload = {
        "model": cfg["model"],
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{cfg['base_url'].rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"], time.time() - t0


def parse_codes(raw: str) -> tuple[list[str], dict]:
    """从模型回答里拿 error_codes；JSON 解析失败就退回正则抓 category.subcategory。"""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            codes = data.get("error_codes") or []
            if isinstance(codes, str):
                codes = [codes]
            return [str(c) for c in codes], data
    except Exception:
        pass
    found = re.findall(r"\b([a-z_]+(?:\.[a-z_]+)?)\b", cleaned)
    keep = [
        t for t in found
        if "." in t and t.split(".")[0] in {
            "syntax", "schema_link", "join", "filter", "aggregation",
            "value", "subquery", "set_ops", "other",
        }
    ]
    return list(dict.fromkeys(keep)), {"raw": raw[:400]}


def normalize(code: str) -> str:
    """容忍模型只写子类名（col_missing）或带反引号的情况。"""
    c = code.strip().strip("`").strip().lower()
    return c


# --------------------------------------------------------------------------- #
# 打分
# --------------------------------------------------------------------------- #


def score_case(case: dict, pred_codes: list[str]) -> dict:
    pred_norm = [normalize(c) for c in pred_codes]
    pred_cats = {c.split(".")[0] for c in pred_norm if "." in c}
    exp_cats = set(case["expected_categories"])
    exp_primary_cat = case["expected_categories"][0]
    exp_codes = [normalize(c) for c in case["expected_codes"]]
    allowed_extra = {normalize(c) for c in ALLOWED_EXTRA.get(case["id"], set())}

    def hit(cand: str, targets: list[str]) -> bool:
        """容忍模型只写子类名（col_missing）或写全（schema_link.col_missing）。"""
        for t in targets:
            if cand == t or t.endswith("." + cand) or cand.endswith("." + t):
                return True
        return False

    extra = [p for p in pred_norm if not hit(p, exp_codes)]
    unreasonable = [p for p in extra if not hit(p, list(allowed_extra))]

    return {
        "primary_cat_hit": exp_primary_cat in pred_cats,
        "cat_exact": pred_cats == exp_cats,
        "primary_code_hit": hit(exp_codes[0], pred_norm),
        "all_codes_hit": all(hit(c, pred_norm) for c in exp_codes),
        "extra": extra,
        "unreasonable_extra": unreasonable,
        "pred_cats": sorted(pred_cats),
        "pred_codes": pred_norm,
    }


def print_summary(results: list[dict], rows: list[dict]) -> None:
    if not results:
        print("\n没有任何用例成功跑完。")
        return
    n = len(results)
    p1 = sum(r["primary_cat_hit"] for r in results)
    p2 = sum(r["cat_exact"] for r in results)
    p3 = sum(r["primary_code_hit"] for r in results)
    p4 = sum(r["all_codes_hit"] for r in results)
    p5 = sum(not r["unreasonable_extra"] for r in results)
    print("\n" + "-" * 72)
    print(f"主根因大类命中   {p1}/{n}  ({p1 / n:.0%})   ← 最重要的指标")
    print(f"主编码命中       {p3}/{n}  ({p3 / n:.0%})")
    print(f"全部编码命中     {p4}/{n}  ({p4 / n:.0%})")
    print(f"无无理多报       {p5}/{n}  ({p5 / n:.0%})   ← 有没有把不沾边的编码也列上")
    print(f"类别集合完全一致 {p2}/{n}  ({p2 / n:.0%})   ← 偏严，模型的合理补充也计入差异")
    secs = [float(r["seconds"]) for r in rows if r.get("seconds") is not None]
    if secs:
        print(f"平均耗时         {sum(secs) / len(secs):.1f}s")
    bad = [r["id"] for r in rows if isinstance(r.get("score"), dict) and r["score"]["unreasonable_extra"]]
    if bad:
        print(f"有无理多报的用例 : {', '.join(bad)}")
    print("-" * 72)
    print("说明：这是「诊断质量」的分数，与端到端是否真的把 SQL 改对是两件事。")


def main() -> int:
    ap = argparse.ArgumentParser(description="纠错诊断质量测试（方法①）")
    ap.add_argument("--dry-run", action="store_true", help="只拼提示词，不调用 API")
    ap.add_argument("--only", default="", help="只跑指定用例 id，逗号分隔")
    ap.add_argument("--rescore", default="", help="不调 API，用已有的 --json 结果文件重新计分")
    ap.add_argument("--json", dest="json_out", default="", help="结果写入 JSON 文件")
    ap.add_argument("--show", action="store_true", help="打印模型原始回答")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--model", default="")
    ap.add_argument("--base-url", default="")
    args = ap.parse_args()

    if not SKILL_MD.exists() or not TAXONOMY_MD.exists():
        print(f"找不到技能文件：\n  {SKILL_MD}\n  {TAXONOMY_MD}", file=sys.stderr)
        return 2

    system_prompt = build_system_prompt()
    cases = CASES
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        cases = [c for c in cases if c["id"] in want]
        missing = want - {c["id"] for c in cases}
        if missing:
            print(f"未知用例 id：{sorted(missing)}", file=sys.stderr)
            return 2

    env = load_dotenv(ENV_FILE)
    cfg = {
        "api_key": os.environ.get("LLM_API_KEY") or env.get("LLM_API_KEY", ""),
        "base_url": args.base_url or os.environ.get("LLM_BASE_URL") or env.get("LLM_BASE_URL", ""),
        "model": args.model or os.environ.get("LLM_MODEL") or env.get("LLM_MODEL", ""),
    }

    print(f"技能文件 : {SKILL_MD.relative_to(REPO)}")
    print(f"分类法   : {TAXONOMY_MD.relative_to(REPO)}")
    print(f"system 提示词长度: {len(system_prompt)} 字符")
    print(f"用例数   : {len(cases)}")

    if args.dry_run:
        for c in cases:
            print(f"\n{'=' * 72}\n[DRY-RUN] {c['id']}  期望={c['expected_codes']}\n{'=' * 72}")
            print(build_user_prompt(c))
        print(f"\n(仅演练：未调用 API。system 提示词 {len(system_prompt)} 字符已就绪)")
        return 0

    if args.rescore:
        data = json.loads(Path(args.rescore).read_text(encoding="utf-8"))
        results, rows = [], []
        for r in data.get("rows", []):
            case = next((c for c in CASES if c["id"] == r.get("id")), None)
            if case is None or "error" in r:
                continue
            s = score_case(case, r.get("predicted", []))
            mark = "✓" if s["primary_cat_hit"] else ("△" if s["pred_cats"] else "✗")
            print(
                f"[{r['id']:<24}] {mark} "
                f"预测={','.join(s['pred_codes']) or '(空)':<38} "
                f"期望={','.join(case['expected_codes'])}"
            )
            results.append(s)
            rows.append({**r, "score": s})
        print(f"\n(重新计分：{args.rescore}，未调用 API)")
        print_summary(results, rows)
        return 0

    if not cfg["api_key"] or not cfg["base_url"] or not cfg["model"]:
        print(f"缺少 LLM 配置（api_key/base_url/model）——请检查 {ENV_FILE} 或环境变量", file=sys.stderr)
        return 2
    print(f"模型     : {cfg['model']} @ {cfg['base_url']}\n")

    results, rows = [], []
    for i, c in enumerate(cases, 1):
        try:
            raw, dt = call_model(cfg, system_prompt, build_user_prompt(c), args.timeout)
        except urllib.error.HTTPError as e:
            print(f"[{i:02d}] {c['id']:<24} ✗ HTTP {e.code}: {e.read()[:200].decode('utf-8', 'ignore')}")
            rows.append({"id": c["id"], "error": f"HTTP {e.code}"})
            continue
        except Exception as e:  # noqa: BLE001
            print(f"[{i:02d}] {c['id']:<24} ✗ 调用失败: {e}")
            rows.append({"id": c["id"], "error": str(e)})
            continue

        codes, parsed = parse_codes(raw)
        s = score_case(c, codes)
        mark = "✓" if s["primary_cat_hit"] else ("△" if s["pred_cats"] else "✗")
        print(
            f"[{i:02d}] {c['id']:<24} {mark} "
            f"预测={','.join(s['pred_codes']) or '(空)':<38} "
            f"期望={','.join(c['expected_codes'])}  {dt:.1f}s"
        )
        if args.show:
            print(f"      根因: {parsed.get('root_cause', parsed.get('raw', ''))[:200]}")
        rows.append({"id": c["id"], "expected": c["expected_codes"], "predicted": s["pred_codes"],
                     "score": s, "seconds": round(dt, 1), "raw": raw})
        results.append(s)

    if not results:
        print("\n没有任何用例成功跑完。")
        return 1

    print_summary(results, rows)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"model": cfg["model"], "rows": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"明细已写入 {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
