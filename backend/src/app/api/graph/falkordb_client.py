from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

# 已做过语义属性预定义的 graph_id 缓存（进程内）
_ENSURED_SEMANTIC_GRAPHS: set[str] = set()

# 语义属性按标签分组——这些属性只在用户配置过的节点上存在，
# 而 FalkorDB 访问「全图从未定义过」的属性会报
# "Attempted to access undefined attribute"
_SEMANTIC_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "Table": ("business_name", "synonyms"),
    "Column": ("business_name", "synonyms", "enum_descriptions"),
}


async def ensure_semantic_attributes(graph, graph_id: str = "") -> None:
    """确保语义属性在全图范围内已定义，避免查询时抛 undefined attribute。

    原理：FalkorDB 只有当属性在整张图中从未出现过时，访问它才会报错；
    一旦有任何节点拥有该属性（哪怕是空串），其余节点访问会返回 null。
    因此用「探针查询探测 → 未定义则统一置空串」的方式预定义，
    且置空是安全的——探针失败意味着全图都没有该属性的值，不会覆盖任何数据。
    """
    cache_key = graph_id or id(graph)
    if cache_key in _ENSURED_SEMANTIC_GRAPHS:
        return
    for label, attrs in _SEMANTIC_ATTRIBUTES.items():
        for attr in attrs:
            try:
                # 探针：用与真实查询相同的访问方式探测属性是否已定义
                await graph.query(
                    f"MATCH (n:{label}) RETURN n.{attr} LIMIT 1"
                )
            except Exception:
                logger.info(
                    "Defining undefined semantic attribute %s.%s in graph %s",
                    label, attr, graph_id or "?",
                )
                try:
                    await graph.query(f"MATCH (n:{label}) SET n.{attr} = ''")
                except Exception:
                    logger.warning(
                        "Failed to define attribute %s.%s in graph %s",
                        label, attr, graph_id or "?", exc_info=True,
                    )
    _ENSURED_SEMANTIC_GRAPHS.add(cache_key)


class FalkorDBClient:
    """兼容层：将旧版类方法调用委托给 app.graphdb.client 单例。"""

    @classmethod
    def _get_client(cls):
        from app.graphdb.client import get_falkordb
        return get_falkordb()

    @classmethod
    async def initialize(cls, host: str = "localhost", port: int = 6379,
                         username: str = "", password: str = "") -> None:
        """已弃用，保留以兼容旧代码。FalkorDB 由 app.graphdb.client 自动管理。"""
        logger.debug("FalkorDBClient.initialize is deprecated; using app.graphdb.client")

    @classmethod
    def get_db(cls):
        return cls._get_client().db

    @classmethod
    async def close(cls) -> None:
        """已弃用，保留以兼容旧代码。"""
        pass

    @classmethod
    def select_graph(cls, graph_id: str):
        return cls._get_client().select_graph(graph_id)

    @classmethod
    async def list_graphs(cls) -> list[str]:
        try:
            keys = await cls._get_client().list_graphs()
            return keys if keys else []
        except Exception:
            return []

    @classmethod
    async def delete_graph(cls, graph_id: str) -> bool:
        try:
            g = cls.select_graph(graph_id)
            await g.delete()
            return True
        except Exception as e:
            logger.error("Delete graph %s failed: %s", graph_id, e)
            return False