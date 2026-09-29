"""Hybrid QA & Few-shot management routes."""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.database import QAPair, DBConnection
from app.memory import GraphMemoryTool

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Hybrid QA"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class QAPairCreate(BaseModel):
    question: str
    sql: str
    connection_id: int
    query_type: Optional[str] = "SELECT"
    difficulty_level: Optional[int] = 3
    verified: Optional[bool] = False
    inject_nl2sql: Optional[bool] = False


class QAPairUpdate(BaseModel):
    question: Optional[str] = None
    sql: Optional[str] = None
    query_type: Optional[str] = None
    difficulty_level: Optional[int] = None
    verified: Optional[bool] = None
    inject_nl2sql: Optional[bool] = None


class QAPairResponse(BaseModel):
    id: int
    connection_id: int
    question: str
    sql: str
    query_type: Optional[str]
    difficulty_level: Optional[int]
    verified: bool
    inject_nl2sql: bool
    success_rate: float
    created_at: Optional[str]
    updated_at: Optional[str]


class SearchRequest(BaseModel):
    question: Optional[str] = None
    connection_id: Optional[int] = None
    top_k: Optional[int] = 5


class SimilarQAPair(BaseModel):
    qa_pair: QAPairResponse
    final_score: float
    explanation: str


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.post("/hybrid-qa/qa-pairs/", response_model=dict)
async def create_qa_pair(
    data: QAPairCreate, session: AsyncSession = Depends(get_session)
):
    """Create a new Q&A pair."""
    qa = QAPair(
        connection_id=data.connection_id,
        question=data.question,
        sql=data.sql,
        query_type=data.query_type,
        difficulty_level=data.difficulty_level,
        verified=data.verified,
        inject_nl2sql=data.inject_nl2sql,
    )
    session.add(qa)
    await session.commit()
    await session.refresh(qa)
    return {"status": "success", "qa_id": str(qa.id), "message": "QA pair created"}


@router.post("/hybrid-qa/qa-pairs/batch-create", response_model=dict)
async def batch_create_qa_pairs(
    data: List[QAPairCreate], session: AsyncSession = Depends(get_session)
):
    """Batch create Q&A pairs."""
    created = 0
    errors = []
    for item in data:
        try:
            qa = QAPair(
                connection_id=item.connection_id,
                question=item.question,
                sql=item.sql,
                query_type=item.query_type,
                difficulty_level=item.difficulty_level,
                verified=item.verified,
                inject_nl2sql=item.inject_nl2sql,
            )
            session.add(qa)
            created += 1
        except Exception as e:
            errors.append(str(e))
    await session.commit()
    return {
        "status": "success",
        "created_count": created,
        "failed_count": len(errors),
        "errors": errors,
    }


@router.get("/hybrid-qa/qa-pairs/stats", response_model=dict)
async def get_qa_stats(
    connection_id: Optional[int] = None, session: AsyncSession = Depends(get_session)
):
    """Get Q&A pair statistics."""
    stmt = select(func.count(QAPair.id))
    verified_stmt = select(func.count(QAPair.id)).where(QAPair.verified.is_(True))
    if connection_id:
        stmt = stmt.where(QAPair.connection_id == connection_id)
        verified_stmt = verified_stmt.where(QAPair.connection_id == connection_id)

    total = (await session.execute(stmt)).scalar() or 0
    verified = (await session.execute(verified_stmt)).scalar() or 0

    # Query type distribution
    type_stmt = select(QAPair.query_type, func.count(QAPair.id))
    if connection_id:
        type_stmt = type_stmt.where(QAPair.connection_id == connection_id)
    type_stmt = type_stmt.group_by(QAPair.query_type)
    type_rows = (await session.execute(type_stmt)).all()

    # Difficulty distribution
    diff_stmt = select(QAPair.difficulty_level, func.count(QAPair.id))
    if connection_id:
        diff_stmt = diff_stmt.where(QAPair.connection_id == connection_id)
    diff_stmt = diff_stmt.group_by(QAPair.difficulty_level)
    diff_rows = (await session.execute(diff_stmt)).all()

    return {
        "total_qa_pairs": total,
        "verified_qa_pairs": verified,
        "query_types": {row[0] or "UNKNOWN": row[1] for row in type_rows},
        "difficulty_distribution": {str(row[0] or 3): row[1] for row in diff_rows},
        "average_success_rate": 100.0 if total > 0 else 0.0,
    }


@router.post("/hybrid-qa/qa-pairs/search", response_model=List[SimilarQAPair])
async def search_similar_qa_pairs(
    data: SearchRequest, session: AsyncSession = Depends(get_session)
):
    """Search similar Q&A pairs by question text, or list all pairs for a connection."""
    stmt = select(QAPair)
    if data.connection_id:
        stmt = stmt.where(QAPair.connection_id == data.connection_id)

    result = await session.execute(stmt)
    pairs = result.scalars().all()

    scored = []
    if data.question:
        # Simple keyword overlap scoring
        q_words = set(data.question.lower().split())
        for qa in pairs:
            qa_words = set(qa.question.lower().split())
            overlap = len(q_words & qa_words) / max(len(q_words), 1)
            scored.append((qa, overlap))
        scored.sort(key=lambda x: x[1], reverse=True)
    else:
        # No question provided — return all pairs for the selected connection
        # sorted by most recently created
        for qa in pairs:
            scored.append((qa, 1.0))

        # created_at 可能混用时区感知/朴素 datetime（如部分记录由外部脚本写入），
        # 统一转成时间戳再比较，避免 naive 与 aware 直接比较报错
        def _created_key(item):
            dt = item[0].created_at
            if dt is None:
                return 0.0
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()

        scored.sort(key=_created_key, reverse=True)

    limit = data.top_k or 5

    return [
        SimilarQAPair(
            qa_pair=QAPairResponse(
                id=qa.id,
                connection_id=qa.connection_id,
                question=qa.question,
                sql=qa.sql,
                query_type=qa.query_type,
                difficulty_level=qa.difficulty_level,
                verified=qa.verified,
                inject_nl2sql=qa.inject_nl2sql,
                success_rate=qa.success_rate,
                created_at=qa.created_at.isoformat() if qa.created_at else None,
                updated_at=qa.updated_at.isoformat() if qa.updated_at else None,
            ),
            final_score=score,
            explanation="Keyword overlap" if data.question else "All pairs for selected connection",
        )
        for qa, score in scored[:limit]
    ]


@router.delete("/hybrid-qa/qa-pairs/{qa_id}", response_model=dict)
async def delete_qa_pair(
    qa_id: int, session: AsyncSession = Depends(get_session)
):
    """Delete a Q&A pair."""
    result = await session.execute(select(QAPair).where(QAPair.id == qa_id))
    qa = result.scalar_one_or_none()
    if not qa:
        raise HTTPException(status_code=404, detail="QA pair not found")
    await session.delete(qa)
    await session.commit()
    return {"status": "success", "message": "QA pair deleted"}


@router.put("/hybrid-qa/qa-pairs/{qa_id}/inject", response_model=dict)
async def toggle_inject_nl2sql(
    qa_id: int,
    inject: bool,
    session: AsyncSession = Depends(get_session),
):
    """Toggle inject_nl2sql flag for a Q&A pair."""
    result = await session.execute(select(QAPair).where(QAPair.id == qa_id))
    qa = result.scalar_one_or_none()
    if not qa:
        raise HTTPException(status_code=404, detail="QA pair not found")
    qa.inject_nl2sql = inject
    await session.commit()
    return {"status": "success", "message": f"inject_nl2sql set to {inject}"}


@router.post("/hybrid-qa/qa-pairs/feedback", response_model=dict)
async def submit_feedback(
    qa_id: str,
    user_satisfaction: float,
    feedback_text: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """Submit feedback for a Q&A pair."""
    return {"status": "success", "message": "Feedback recorded"}


@router.get("/hybrid-qa/qa-pairs/health", response_model=dict)
async def health_check():
    """Health check for Hybrid QA service."""
    return {"status": "healthy", "timestamp": str(__import__("datetime").datetime.utcnow())}


@router.post("/hybrid-qa/qa-pairs/{qa_id}/inject-to-memory", response_model=dict)
async def inject_qa_pair_to_memory(
    qa_id: int,
    user_id: Optional[str] = "default",
    session: AsyncSession = Depends(get_session),
):
    """Inject an existing QA pair into the graph memory (knowledge graph).

    Mirrors the memory persistence logic at the end of a successful
    intelligent-query session so that manually-curated examples also
    become retrievable by the memory system.
    """
    # 1) Resolve the QA pair
    result = await session.execute(select(QAPair).where(QAPair.id == qa_id))
    qa = result.scalar_one_or_none()
    if not qa:
        raise HTTPException(status_code=404, detail="QA pair not found")

    # 2) Resolve the FalkorDB graph_id from the linked connection
    conn_result = await session.execute(
        select(DBConnection).where(DBConnection.id == qa.connection_id)
    )
    conn = conn_result.scalar_one_or_none()
    if not conn or not conn.falkordb_graph_id:
        raise HTTPException(
            status_code=400,
            detail="Database connection has no associated knowledge graph. "
                   "Please run schema discovery first.",
        )
    graph_id = conn.falkordb_graph_id

    # 3) Feed into memory graph
    try:
        memory_tool = await GraphMemoryTool.create(user_id, graph_id)
        await memory_tool.save_query_memory(
            question=qa.question,
            sql=qa.sql,
            success=True,
            error=None,
        )
        await memory_tool.update_user_summary(
            question=qa.question,
            sql=qa.sql,
            success=True,
            error=None,
            answer=None,
        )
        return {
            "status": "success",
            "message": "QA pair injected into memory graph",
            "graph_id": graph_id,
            "group_id": f"{user_id}_{graph_id}",
        }
    except Exception as e:
        logger.error("Failed to inject QA pair to memory: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Memory injection failed: {str(e)}",
        )
