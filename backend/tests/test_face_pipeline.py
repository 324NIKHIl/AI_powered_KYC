"""run_face_verification end-to-end with the face model and database replaced by fakes."""

import base64

import cv2
import numpy as np
import pytest

from models.verification import KycStatus, RejectionReason
from services import verification_service as vs
from services.face_service import FaceMatchResult
from tests.test_liveness_identity import BOX, moire, skin_frame


def b64(img):
    return base64.b64encode(cv2.imencode(".jpg", img)[1].tobytes()).decode()


@pytest.fixture
def harness(monkeypatch):
    state = {"session": {"document_face_path": "ref.jpg", "document_status": "VALID", "document_risk": 0.05},
             "similarity": 0.62, "reason": None, "saved": None}

    async def get_session(_sid):
        return state["session"]

    async def upsert(_sid, _session, updates):
        state["saved"] = updates

    def fake_verify_faces(_path, _img):
        return FaceMatchResult(verified=state["reason"] is None, similarity=state["similarity"],
                               rejection_reason=state["reason"], live_face_box=BOX if state["reason"] is None else None)

    monkeypatch.setattr(vs, "get_session", get_session)
    monkeypatch.setattr(vs, "_upsert_verification", upsert)
    monkeypatch.setattr(vs, "verify_faces", fake_verify_faces)
    monkeypatch.setattr(vs, "save_image", lambda *a, **k: "x.jpg")
    return state


async def run(frame, extras=(), client_live=True):
    return await vs.run_face_verification("sid", b64(frame), client_live, [b64(e) for e in extras])


def live_frames():
    return skin_frame(1), [skin_frame(i) for i in (2, 3, 4)]


async def test_genuine_user_is_verified(harness):
    f, extra = live_frames()
    r = await run(f, extra)
    assert r.kyc_status == KycStatus.VERIFIED and r.verified and r.face_match_status == "MATCH"
    assert r.liveness["status"] == "PASS" and r.deepfake["level"] == "LOW"
    assert harness["saved"]["kyc_status"] == "VERIFIED" and harness["saved"]["final_decision"].value == "APPROVED"


async def test_different_person_is_rejected(harness):
    harness["similarity"] = 0.08
    f, extra = live_frames()
    r = await run(f, extra)
    assert r.kyc_status == KycStatus.REJECTED and not r.verified and r.face_match_status == "NO_MATCH"


async def test_borderline_similarity_goes_to_manual_review(harness):
    harness["similarity"] = 0.27
    f, extra = live_frames()
    assert (await run(f, extra)).kyc_status == KycStatus.MANUAL_REVIEW_REQUIRED


async def test_screen_replay_is_suspicious_even_if_client_says_live(harness):
    r = await run(moire(skin_frame()), client_live=True)
    assert r.kyc_status == KycStatus.SUSPICIOUS and r.liveness["status"] == "FAIL" and not r.verified


async def test_photo_held_up_static_frames_suspicious(harness):
    f = skin_frame()
    r = await run(f, [f.copy(), f.copy(), f.copy()])
    assert r.kyc_status == KycStatus.SUSPICIOUS


async def test_client_failure_flag_blocks_verification(harness):
    f, extra = live_frames()
    r = await run(f, extra, client_live=False)
    assert r.kyc_status == KycStatus.MANUAL_REVIEW_REQUIRED and not r.verified


async def test_unavailable_document_verification_blocks_approval(harness):
    harness["session"]["document_status"] = "VERIFICATION_UNAVAILABLE"
    f, extra = live_frames()
    r = await run(f, extra)
    assert r.kyc_status == KycStatus.VERIFICATION_UNAVAILABLE and not r.verified
    assert r.final_decision.value == "PENDING"


async def test_suspicious_document_blocks_even_with_perfect_face(harness):
    harness["session"]["document_status"] = "SUSPICIOUS"
    f, extra = live_frames()
    assert (await run(f, extra)).kyc_status == KycStatus.SUSPICIOUS


async def test_no_face_in_capture_asks_for_retake_not_approval(harness):
    harness["reason"] = RejectionReason.NO_LIVE_FACE
    harness["similarity"] = 0.0
    f, extra = live_frames()
    r = await run(f, extra)
    assert r.kyc_status == KycStatus.MANUAL_REVIEW_REQUIRED and "No face detected in live capture" in r.reason


async def test_missing_session_is_rejected(harness):
    harness["session"] = None
    f, _ = live_frames()
    r = await run(f)
    assert not r.verified and "Session not found" in r.reason


async def test_bad_extra_frames_do_not_crash(harness):
    f, _ = live_frames()
    r = await vs.run_face_verification("sid", b64(f), True, ["not-base64!!", "AAAA"])
    assert r.kyc_status is not None
