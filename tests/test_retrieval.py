"""Schema 检索的合并去重 —— 四路召回（表向量 / 列向量 / 图遍历）最后并到一起的那一步。

去重规则很关键：同名表**保留第一次出现的那条**，而调用方把「表级向量命中」
排在最前面（retrieval.py Phase 4），所以表级命中的列集合优先级最高。
"""
from app.api.graph.retrieval import _unique


def _row(name, desc="", cols=None):
    """按 Phase 2/3 的六元组结构造一条假记录。"""
    return (name, desc, "Foreign keys: ", "", "", cols if cols is not None else [])


def test_同名表只保留第一次出现的那条():
    rows = [_row("tracks", "A"), _row("albums", "B"), _row("tracks", "C")]
    out = _unique(rows)
    assert [r[0] for r in out] == ["tracks", "albums"]
    assert out[0][1] == "A", "重名时应保留先出现的那条，而不是被覆盖"


def test_保持插入顺序():
    rows = [_row("c"), _row("a"), _row("b")]
    assert [r[0] for r in _unique(rows)] == ["c", "a", "b"]


def test_列集合会被转成普通dict():
    """FalkorDB 返回的 map 类型可能不是 dict，需要统一成 dict 才能序列化。"""
    rows = [_row("t", cols=[{"columnName": "a"}])]
    out = _unique(rows)
    assert out[0][5] == [{"columnName": "a"}]
    assert isinstance(out[0][5][0], dict)


def test_非dict的列集合按键值对转换():
    rows = [_row("t", cols=[[("columnName", "a")]])]
    assert _unique(rows)[0][5] == [{"columnName": "a"}]


def test_空输入返回空列表():
    assert _unique([]) == []


def test_列集合不是列表时原样保留():
    rows = [("t", "", "", "", "", "not-a-list")]
    assert _unique(rows)[0][5] == "not-a-list"
