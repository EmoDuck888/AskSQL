from __future__ import annotations
import json, logging, asyncio
from itertools import combinations
from app.api.config import settings
from app.api.embeddings import get_embedding_backend
from app.api.graph.falkordb_client import FalkorDBClient, ensure_semantic_attributes

logger = logging.getLogger(__name__)

FIND_PROMPT = """You are an expert in analyzing natural language queries into SQL table/column descriptions.
Describe tables by BUSINESS PURPOSE, columns by DATA they contain. Do NOT guess names. Max 5 each.
Database context: {db_description}. Previous queries: {previous_queries}
Return JSON: {"tables_descriptions": [{"name":"label","description":"this table stores..."}],
               "columns_descriptions": [{"name":"label","description":"this column contains..."}]}"""

async def _get_db_desc(graph_id: str) -> tuple[str, str]:
    g = FalkorDBClient.select_graph(graph_id)
    r = await g.query("MATCH (d:Database) RETURN d.description, d.url")
    if r.result_set:
        return r.result_set[0][0], r.result_set[0][1]
    return "No description", "No URL"

async def _q(graph, query: str, params: dict = None, timeout: int = 60):
    r = await graph.query(query, params or {}, timeout=timeout)
    return r.result_set

async def _find_tables(graph, embeddings: list) -> list:
    q = """CALL db.idx.vector.queryNodes('Table','embedding',3,vecf32($e)) YIELD node, score
           MATCH (node)-[:BELONGS_TO]-(columns)
           RETURN node.name, node.description, node.foreign_keys, node.business_name, node.synonyms,
                  collect({columnName:columns.name,description:columns.description,
                           dataType:columns.type,keyType:columns.key_type,nullable:columns.nullable,
                           businessName:columns.business_name,synonyms:columns.synonyms,
                           enumDescriptions:columns.enum_descriptions}), score"""
    res = []
    for e in embeddings:
        rows = await _q(graph, q, {"e": e})
        res.extend(rows)
    return res

async def _find_by_cols(graph, embeddings: list) -> list:
    q = """CALL db.idx.vector.queryNodes('Column','embedding',3,vecf32($e)) YIELD node, score
           MATCH (node)-[:BELONGS_TO]-(table)-[:BELONGS_TO]-(columns)
           RETURN table.name, table.description, table.foreign_keys, table.business_name, table.synonyms,
                  collect({columnName:columns.name,description:columns.description,
                           dataType:columns.type,keyType:columns.key_type,nullable:columns.nullable,
                           businessName:columns.business_name,synonyms:columns.synonyms,
                           enumDescriptions:columns.enum_descriptions}), score"""
    res = []
    for e in embeddings:
        rows = await _q(graph, q, {"e": e})
        res.extend(rows)
    return res

async def _sphere(graph, names: list[str]) -> list:
    q = """MATCH (node:Table {name: $n})
           MATCH (node)-[:BELONGS_TO]-(col)-[:REFERENCES]-()-[:BELONGS_TO]-(tref)
           WITH tref MATCH (tref)-[:BELONGS_TO]-(cols)
           RETURN tref.name, tref.description, tref.foreign_keys, tref.business_name, tref.synonyms,
                  collect({columnName:cols.name,description:cols.description,
                           dataType:cols.type,keyType:cols.key_type,nullable:cols.nullable,
                           businessName:cols.business_name,synonyms:cols.synonyms,
                           enumDescriptions:cols.enum_descriptions})"""
    res = []
    for n in names:
        try:
            rows = await _q(graph, q, {"n": n})
            res.extend(rows)
        except Exception as e:
            logger.debug("Sphere search failed for %s: %s", n, e)
    return res

async def _connecting(graph, names: list[str]) -> list:
    if len(names) < 2: return []
    pairs = [list(p) for p in combinations(names, 2)]
    q = """UNWIND $pairs AS pair
           MATCH (a:Table {name: pair[0]}), (b:Table {name: pair[1]})
           WITH a,b MATCH p=allShortestPaths((a)-[*..4]-(b))
           UNWIND nodes(p) AS nd WITH DISTINCT nd
           WHERE 'Table' IN labels(nd) OR ('Column' IN labels(nd) AND nd.key_type='PRI')
           WITH nd, 'Table' IN labels(nd) AS ist, 'Column' IN labels(nd) AND nd.key_type='PRI' AS isp
           OPTIONAL MATCH (nd)-[:BELONGS_TO]->(pt:Table) WHERE isp
           WITH CASE WHEN ist THEN nd WHEN isp THEN pt ELSE null END AS tgt WHERE tgt IS NOT NULL
           WITH DISTINCT tgt MATCH (col:Column)-[:BELONGS_TO]->(tgt)
           RETURN tgt.name, tgt.description, tgt.foreign_keys, tgt.business_name, tgt.synonyms,
                  collect({columnName:col.name,description:col.description,
                           dataType:col.type,keyType:col.key_type,nullable:col.nullable,
                           businessName:col.business_name,synonyms:col.synonyms,
                           enumDescriptions:col.enum_descriptions})"""
    try:
        return await _q(graph, q, {"pairs": pairs}, timeout=120)
    except Exception as e:
        logger.error("Connecting search failed: %s", e)
        return []

def _unique(tbls: list) -> list:
    u = {}
    for r in tbls:
        nm = r[0]
        if nm not in u:
            lst = list(r)
            # The columns list is at index 5 (after name, desc, fk, business_name, synonyms)
            if len(lst) > 5 and isinstance(lst[5], list):
                lst[5] = [dict(od) if not isinstance(od, dict) else od for od in lst[5]]
            u[nm] = lst
    return list(u.values())

def _fmt(tbls: list) -> str:
    lines = []
    for r in tbls:
        nm = r[0]
        desc = r[1] if len(r) > 1 else ""
        fk = r[2] if len(r) > 2 else ""
        business_name = r[3] if len(r) > 3 else ""
        synonyms = r[4] if len(r) > 4 else ""
        cols = r[5] if len(r) > 5 else []

        display_name = business_name or nm
        lines.append(f"\nTable: {nm}")
        if business_name:
            lines.append(f"  Business Name: {business_name}")
        if synonyms:
            lines.append(f"  Synonyms: {synonyms}")
        if desc:
            lines.append(f"  Description: {desc}")
        if fk and fk != "Foreign keys: ":
            lines.append(f"  {fk}")
        lines.append("  Columns:")
        for c in cols:
            if isinstance(c, dict):
                col_name = c.get('columnName', '?')
                col_biz = c.get('businessName', '')
                col_syn = c.get('synonyms', '')
                col_enum = c.get('enumDescriptions', '')
                col_desc = c.get('description', '')
                col_type = c.get('dataType', '?')
                key_marker = 'PK' if c.get('keyType') == 'PRI' else 'FK' if c.get('keyType') == 'FK' else ''

                parts = [f"    - {col_name} ({col_type})"]
                if key_marker:
                    parts.append(f" [{key_marker}]")
                parts.append(":")
                if col_biz:
                    parts.append(f" business_name={col_biz};")
                if col_syn:
                    parts.append(f" synonyms={col_syn};")
                if col_desc:
                    parts.append(f" description={col_desc};")
                if col_enum:
                    parts.append(f" enum={col_enum};")
                lines.append("".join(parts))
    return "\n".join(lines)

async def find_relevant_schema(graph_id: str, user_query: str,
                               previous_queries: list[str] | None = None,
                               db_description: str = "") -> dict:
    g = FalkorDBClient.select_graph(graph_id)
    # 预定义语义属性，避免访问未定义属性报错（详见 falkordb_client.ensure_semantic_attributes）
    await ensure_semantic_attributes(g, graph_id)
    if not db_description:
        db_description, _ = await _get_db_desc(graph_id)
    prev = "\n".join(f"Q{i+1}: {q}" for i, q in enumerate(previous_queries or [])) or "None"

    # Phase 1: LLM 生成描述
    data: dict = {}
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        model = ChatOpenAI(
            api_key=settings.LLM_API_KEY or settings.OPENAI_API_KEY or settings.DEEPSEEK_API_KEY,
            base_url=settings.LLM_BASE_URL or None,
            model=settings.LLM_MODEL,
            temperature=0,
        )
        messages = [
            SystemMessage(
                content=FIND_PROMPT.replace("{db_description}", db_description).replace("{previous_queries}", prev)
            ),
            HumanMessage(
                content=json.dumps(
                    {
                        "previous_user_queries": previous_queries or [],
                        "user_query": user_query,
                    }
                )
            ),
        ]
        result = await model.ainvoke(
            messages, response_format={"type": "json_object"}
        )
        raw = result.content
        if raw:
            # Strip markdown fences and whitespace
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("\n", 1)[0]
            cleaned = cleaned.strip()
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                data = parsed
    except Exception as e:
        logger.error("LLM description gen failed: %s", e)

    if not isinstance(data, dict) or "tables_descriptions" not in data:
        data = {
            "tables_descriptions": [{"description": user_query}],
            "columns_descriptions": [],
        }

    # Phase 2: 向量搜索
    td = data.get("tables_descriptions", [])
    cd = data.get("columns_descriptions", [])
    all_d = [d["description"] for d in td] + [d["description"] for d in cd]
    if not all_d: all_d = [user_query]
    backend = get_embedding_backend()
    all_e = backend.embed(all_d)
    te = all_e[:len(td)]; ce = all_e[len(td):]

    tasks = []
    if te: tasks.append(_find_tables(g, te))
    if ce: tasks.append(_find_by_cols(g, ce))
    results = await asyncio.gather(*tasks) if tasks else []
    tbls_d = results[0] if te else []
    tbls_c = results[1] if (te and ce and len(results)>1) else []

    # Phase 3: 图遍历
    found_names = [t[0] for t in tbls_d] if tbls_d else []
    if found_names:
        sp, cnx = await asyncio.gather(_sphere(g, found_names), _connecting(g, found_names))
    else:
        sp, cnx = [], []

    # Phase 4: 合并
    all_t = _unique(tbls_d + tbls_c + cnx + sp)
    return {"tables": [t[0] for t in all_t], "schema_text": _fmt(all_t),
            "table_count": len(all_t), "query_method": "llm_mediated_retrieval"}