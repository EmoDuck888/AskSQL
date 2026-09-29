from __future__ import annotations
import json, logging

from app.api.embeddings import get_embedding_backend
from app.api.graph.falkordb_client import FalkorDBClient

logger = logging.getLogger(__name__)


def _desc(kind: str, props: dict) -> str:
    if kind == "table":
        return f"Table: {props.get('name','')}. Contains {props.get('description', props.get('name',''))}."
    else:
        desc = f"Column: {props.get('table_name','')}.{props.get('name','')}. Type: {props.get('type','unknown')}."
        samples = props.get("sample_values", [])
        if samples:
            desc += f" Samples: {', '.join(str(s) for s in samples[:5])}"
        return desc

async def load_schema_to_graph(
    graph_id: str, db_name: str, db_url: str,
    tables: list[dict], relationships: list[dict], db_description: str = "",
) -> dict:
    try:
        g = FalkorDBClient.select_graph(graph_id)
        backend = get_embedding_backend()
        vec_sz = backend.vector_size

        # 清理旧图，避免 stale 节点干扰向量搜索
        try:
            await g.delete()
            g = FalkorDBClient.select_graph(graph_id)
            logger.info("Cleared existing graph: %s", graph_id)
        except Exception as e:
            logger.debug("Graph delete (may not exist): %s", e)

        # 向量索引
        try:
            await g.query("CREATE VECTOR INDEX FOR (t:Table) ON (t.embedding) OPTIONS {dimension:$s, similarityFunction:'cosine'}", {"s": vec_sz})
            await g.query("CREATE VECTOR INDEX FOR (c:Column) ON (c.embedding) OPTIONS {dimension:$s, similarityFunction:'cosine'}", {"s": vec_sz})
            await g.query("CREATE INDEX FOR (t:Table) ON (t.name)")
        except Exception as e:
            logger.debug("Index create (may exist): %s", e)
        # Database 节点
        await g.query("MERGE (d:Database {name: $n}) SET d.description=$d, d.url=$u",
                      {"n": db_name, "d": db_description or f"Database: {db_name}", "u": db_url})
        tc = cc = rc = 0
        for tbl in tables:
            tn = tbl["table_name"]
            td = tbl.get("description", "")
            emb = backend.embed([_desc("table", {"name": tn, "description": td})])
            fk_json = json.dumps([{"source_column": r["source_column"], "target_table": r["to"], "target_column": r["target_column"]}
                                  for r in relationships if r.get("from") == tn])
            await g.query("MERGE (t:Table {name: $n}) SET t.description=$d, t.embedding=vecf32($e), t.foreign_keys=$f",
                          {"n": tn, "d": td or f"Table: {tn}", "e": emb[0], "f": fk_json})
            tc += 1
            cols = tbl.get("columns", [])
            col_descs = [_desc("column", {"table_name": tn, "name": c["column_name"],
                              "type": c.get("data_type","unknown"), "description": c.get("description",""),
                              "sample_values": c.get("sample_values",[])}) for c in cols]
            col_embs = backend.embed(col_descs) if col_descs else []
            for idx, c in enumerate(cols):
                cn = c["column_name"]
                kt = "PRI" if c.get("is_primary_key") else ("FK" if c.get("is_foreign_key") else "")
                await g.query("""MATCH (t:Table {name: $tn}) MERGE (c:Column {name: $cn})-[:BELONGS_TO]->(t)
                   SET c.type=$ty, c.nullable=$nu, c.key_type=$kt, c.description=$d, c.embedding=vecf32($e)""",
                   {"tn": tn, "cn": cn, "ty": c.get("data_type","unknown"), "nu": str(c.get("is_nullable",True)),
                    "kt": kt, "d": c.get("description",""), "e": col_embs[idx] if idx < len(col_embs) else []})
                cc += 1
        for rel in relationships:
            try:
                await g.query("""MATCH (src:Column {name: $sc})-[:BELONGS_TO]->(:Table {name: $st})
                   MATCH (tgt:Column {name: $tc})-[:BELONGS_TO]->(:Table {name: $tt})
                   MERGE (src)-[r:REFERENCES]->(tgt) SET r.note=$note""",
                   {"sc": rel["source_column"], "st": rel["from"], "tc": rel["target_column"],
                    "tt": rel["to"], "note": rel.get("note","")})
                rc += 1
            except Exception as e:
                logger.warning("FK fail: %s", e)
        logger.info("Graph loaded: %d tbl, %d col, %d rel", tc, cc, rc)
        return {"success": True, "table_count": tc, "column_count": cc, "relationship_count": rc,
                "message": f"Loaded {tc} tables, {cc} columns, {rc} relationships"}
    except Exception as e:
        logger.error("Load schema failed: %s", e)
        return {"success": False, "message": str(e), "table_count": 0}