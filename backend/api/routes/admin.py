"""
Admin dashboard API routes.
GET /api/verification-history  — paginated list of all verifications
GET /api/stats                 — aggregate counts and rates
GET /api/verification/{id}     — single verification detail
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from models.verification import VerificationStats

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/verification-history",
    status_code=status.HTTP_200_OK,
    summary="Paginated list of verification records",
)
async def get_verification_history(
    page:    int = Query(default=1, ge=1),
    limit:   int = Query(default=20, ge=1, le=100),
    decision: Optional[str] = Query(default=None, description="Filter: APPROVED | REJECTED | PENDING"),
):
    from database.mongodb import verifications_col

    col    = verifications_col()
    skip   = (page - 1) * limit
    query: dict = {}
    if decision:
        query["final_decision"] = decision.upper()

    cursor = col.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    records = await cursor.to_list(length=limit)
    total   = await col.count_documents(query)

    return {
        "records":     records,
        "total":       total,
        "page":        page,
        "limit":       limit,
        "total_pages": (total + limit - 1) // limit,
    }


@router.get(
    "/stats",
    response_model=VerificationStats,
    summary="Aggregate verification statistics",
)
async def get_stats():
    from database.mongodb import verifications_col

    col = verifications_col()

    pipeline = [
        {
            "$group": {
                "_id": "$final_decision",
                "count": {"$sum": 1},
                "avg_sim": {"$avg": "$similarity_score"},
            }
        }
    ]
    cursor = col.aggregate(pipeline)
    groups = await cursor.to_list(length=10)

    stats = VerificationStats()
    total_sim = 0.0
    sim_count = 0

    for g in groups:
        decision = g["_id"] or "PENDING"
        count    = g["count"]
        stats.total += count
        if decision == "APPROVED":
            stats.approved = count
        elif decision == "REJECTED":
            stats.rejected = count
        else:
            stats.pending = count
        if g.get("avg_sim") is not None:
            total_sim += g["avg_sim"] * count
            sim_count += count

    stats.approval_rate = round(stats.approved / stats.total, 4) if stats.total > 0 else 0.0
    stats.avg_similarity = round(total_sim / sim_count, 4) if sim_count > 0 else 0.0

    return stats


@router.get(
    "/verification/{session_id}",
    summary="Get detailed verification record by session ID",
)
async def get_verification_detail(session_id: str):
    from database.mongodb import verifications_col

    col    = verifications_col()
    record = await col.find_one({"session_id": session_id}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail=f"Verification not found for session: {session_id}")
    logger.info(
        "[%s] Result detail response final_decision=%s verified=%s similarity=%s reason=%s",
        session_id,
        record.get("final_decision"),
        record.get("verified"),
        record.get("similarity_score"),
        record.get("reason") or record.get("rejection_reason"),
    )
    return record


@router.delete(
    "/verification/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a verification record (admin only)",
)
async def delete_verification(session_id: str):
    from database.mongodb import verifications_col, sessions_col

    v_col  = verifications_col()
    s_col  = sessions_col()
    result = await v_col.delete_one({"session_id": session_id})
    await s_col.delete_one({"session_id": session_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Record not found")
