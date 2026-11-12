"""
Admin dashboard API routes.
GET /api/verification-history  — paginated list of all verifications
GET /api/stats                 — aggregate counts and rates
GET /api/verification/{id}     — single verification detail
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from api.admin_auth import LoginRequest, login_admin, require_admin
from models.verification import VerificationStats

logger = logging.getLogger(__name__)
router = APIRouter()


class DetailsUpdate(BaseModel):
    extracted_fields: dict[str, Optional[str]]
    reason: str = Field(min_length=3, max_length=1000)


class DecisionUpdate(BaseModel):
    decision: str
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/admin/login", summary="Sign in as admin")
async def admin_login(credentials: LoginRequest):
    return login_admin(credentials)


@router.get(
    "/verification-history",
    status_code=status.HTTP_200_OK,
    summary="Paginated list of verification records",
)
async def get_verification_history(
    page:    int = Query(default=1, ge=1),
    limit:   int = Query(default=20, ge=1, le=100),
    decision: Optional[str] = Query(default=None, description="Filter: APPROVED | REJECTED | PENDING"),
    kyc_status: Optional[str] = Query(
        default=None,
        description="Filter: VERIFIED | REJECTED | SUSPICIOUS | VERIFICATION_UNAVAILABLE | MANUAL_REVIEW_REQUIRED",
    ),
    admin: str = Depends(require_admin),
):
    from database.mongodb import verifications_col

    col    = verifications_col()
    skip   = (page - 1) * limit
    query: dict = {}
    if decision:
        query["final_decision"] = decision.upper()
    if kyc_status:
        query["kyc_status"] = kyc_status.upper()

    cursor = col.find(query, {"_id": 0, "verification_provider": 0}).sort("created_at", -1).skip(skip).limit(limit)
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
async def get_stats(admin: str = Depends(require_admin)):
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
async def get_verification_detail(session_id: str, admin: str = Depends(require_admin)):
    from database.mongodb import verifications_col

    col    = verifications_col()
    record = await col.find_one({"session_id": session_id}, {
        "_id": 0, "verification_provider": 0, "admin_audit": 0, "manual_review": 0,
    })
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


@router.get("/admin/verification/{session_id}/face-image/{image_type}", summary="Get a face image for admin review")
async def get_verification_face_image(
    session_id: str,
    image_type: str,
    admin: str = Depends(require_admin),
):
    from database.mongodb import verifications_col

    field_by_type = {"document": "document_face_path", "live": "live_face_path"}
    field = field_by_type.get(image_type)
    if not field:
        raise HTTPException(status_code=404, detail="Face image type not found")
    record = await verifications_col().find_one({"session_id": session_id}, {"_id": 0, field: 1})
    image_path = record.get(field) if record else None
    if not image_path:
        raise HTTPException(status_code=404, detail="Face image is not available")

    candidate = Path(image_path).resolve()
    allowed_dirs = {
        (Path(os.getenv("UPLOAD_DIR", "uploads")) / "faces").resolve(),
        Path("uploads/faces").resolve(),
    }
    if not any(candidate.is_relative_to(root) for root in allowed_dirs):
        raise HTTPException(status_code=404, detail="Face image is not available")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Face image is not available")
    return FileResponse(candidate, media_type="image/jpeg")


@router.delete(
    "/verification/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a verification record (admin only)",
)
async def delete_verification(session_id: str, admin: str = Depends(require_admin)):
    from database.mongodb import verifications_col, sessions_col

    v_col  = verifications_col()
    s_col  = sessions_col()
    result = await v_col.delete_one({"session_id": session_id})
    await s_col.delete_one({"session_id": session_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Record not found")


@router.put("/admin/verification/{session_id}/details", summary="Correct extracted identity details")
async def update_verification_details(session_id: str, body: DetailsUpdate, admin: str = Depends(require_admin)):
    from database.mongodb import verifications_col

    allowed = {"name", "dob", "gender", "id_number", "address"}
    if set(body.extracted_fields) - allowed:
        raise HTTPException(status_code=422, detail="Unsupported extracted detail field")
    col = verifications_col()
    record = await col.find_one({"session_id": session_id}, {"_id": 0, "extracted_fields": 1})
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    before = record.get("extracted_fields") or {}
    after = {**before, **body.extracted_fields}
    changed = {key: {"from": before.get(key), "to": after.get(key)}
               for key in body.extracted_fields if before.get(key) != after.get(key)}
    now = datetime.now(timezone.utc)
    await col.update_one({"session_id": session_id}, {
        "$set": {"extracted_fields": after, "updated_at": now},
        "$push": {"admin_audit": {"action": "DETAILS_EDITED", "admin": admin,
                                   "reason": body.reason, "changes": changed, "at": now}},
    })
    return {"session_id": session_id, "extracted_fields": after, "changes": changed}


@router.put("/admin/verification/{session_id}/decision", summary="Record a manual verification decision")
async def update_verification_decision(session_id: str, body: DecisionUpdate, admin: str = Depends(require_admin)):
    from database.mongodb import verifications_col

    decision = body.decision.upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise HTTPException(status_code=422, detail="Decision must be APPROVED or REJECTED")
    col = verifications_col()
    now = datetime.now(timezone.utc)
    current = await col.find_one({"session_id": session_id}, {
        "_id": 0, "final_decision": 1, "kyc_status": 1, "verified": 1,
        "automated_decision_snapshot": 1,
    })
    if not current:
        raise HTTPException(status_code=404, detail="Record not found")
    snapshot = current.get("automated_decision_snapshot") or {
        key: current.get(key) for key in ("final_decision", "kyc_status", "verified")
    }
    updated = await col.update_one({"session_id": session_id}, {
        "$set": {
            "final_decision": decision,
            "kyc_status": "VERIFIED" if decision == "APPROVED" else "REJECTED",
            "verified": decision == "APPROVED",
            "status": decision.lower(),
            "manual_review": {"decision": decision, "reason": body.reason, "admin": admin, "at": now},
            "decision_source": "MANUAL",
            "automated_decision_snapshot": snapshot,
            "updated_at": now,
        },
        "$push": {"admin_audit": {"action": "DECISION_RECORDED", "admin": admin,
                                   "decision": decision, "reason": body.reason, "at": now}},
    })
    if not updated.matched_count:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"session_id": session_id, "decision": decision, "kyc_status": "VERIFIED" if decision == "APPROVED" else "REJECTED"}
