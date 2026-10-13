import cv2
import numpy as np
import pytest

from models.verification import KycStatus, VerificationStatus
from services.kyc.deepfake import DeepfakeResult, assess_face_alteration
from services.kyc.identity import FaceMatch, classify_similarity, decide_identity
from services.kyc.liveness import LivenessResult, LivenessStatus, assess_liveness

BOX = [160, 100, 320, 300]


def skin_frame(seed=1, h=480, w=640):
    """A coloured, textured, face-like frame that a live webcam might produce."""
    rng = np.random.default_rng(seed)
    bg = np.full((h, w, 3), (120, 130, 140), np.float32)
    cv2.ellipse(bg, (320, 250), (130, 170), 0, 0, 360, (110, 150, 205), -1)      # skin-toned face
    img = bg + rng.normal(0, 7, bg.shape)
    img = cv2.GaussianBlur(img.astype(np.float32), (0, 0), 0.8)
    img += rng.normal(0, 3, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def moire(img):
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    grid = (0.75 + 0.25 * np.sin(2 * np.pi * xx / 3.1) * np.sin(2 * np.pi * yy / 3.1))[..., None]
    out = np.clip(img * grid, 0, 255).astype(np.uint8)
    return cv2.resize(cv2.resize(out, (400, 300), interpolation=cv2.INTER_NEAREST), img.shape[1::-1])


# ── Liveness ──────────────────────────────────────────────────────────────────

def test_natural_frames_pass():
    frames = [skin_frame(seed=i) for i in range(4)]
    r = assess_liveness(frames[0], BOX, frames[1:])
    assert r.status == LivenessStatus.PASS and r.attack_score < 0.4


def test_screen_replay_fails():
    assert assess_liveness(moire(skin_frame()), BOX).status == LivenessStatus.FAIL


def test_identical_frames_static_image_fails():
    f = skin_frame()
    r = assess_liveness(f, BOX, [f.copy(), f.copy(), f.copy()])
    assert r.status == LivenessStatus.FAIL and any("identical" in x for x in r.reasons)


def test_blackandwhite_print_is_flagged():
    gray = cv2.cvtColor(cv2.GaussianBlur(skin_frame(), (0, 0), 2.5), cv2.COLOR_BGR2GRAY)
    r = assess_liveness(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), BOX)
    assert r.status != LivenessStatus.PASS


def test_client_claim_can_tighten_but_never_loosen():
    f = skin_frame()
    frames = [skin_frame(seed=i) for i in range(1, 4)]
    assert assess_liveness(f, BOX, frames, client_challenge_passed=False).status == LivenessStatus.UNCERTAIN
    # "client says live" must not rescue a screen replay
    assert assess_liveness(moire(f), BOX, client_challenge_passed=True).status == LivenessStatus.FAIL


# ── Face-alteration heuristics ────────────────────────────────────────────────

def test_clean_frame_low_alteration_risk():
    assert assess_face_alteration(skin_frame(), BOX).level == "LOW"


def test_skin_tone_discontinuity_raises_risk():
    f = skin_frame().astype(np.int16)
    f[100:400, 190:450] = np.clip(f[100:400, 190:450] + np.array([-60, 20, 70]), 0, 255)   # pasted, differently-toned face
    r = assess_face_alteration(f.astype(np.uint8), BOX)
    assert r.risk > 0.1 and "skin_tone_break" in r.signals


def test_no_face_box_is_not_a_pass_or_fail():
    r = assess_face_alteration(skin_frame(), None)
    assert r.level == "LOW" and r.reasons


# ── Face match tri-state (configurable) ───────────────────────────────────────

def test_similarity_classification(monkeypatch):
    assert classify_similarity(0.50) == FaceMatch.MATCH
    assert classify_similarity(0.32) == FaceMatch.MATCH
    assert classify_similarity(0.27) == FaceMatch.UNCERTAIN
    assert classify_similarity(0.10) == FaceMatch.NO_MATCH
    monkeypatch.setenv("FACE_SIMILARITY_THRESHOLD", "0.5")
    monkeypatch.setenv("FACE_NO_MATCH_THRESHOLD", "0.4")
    assert classify_similarity(0.45) == FaceMatch.UNCERTAIN and classify_similarity(0.55) == FaceMatch.MATCH


# ── Final decision precedence ─────────────────────────────────────────────────

PASS_LIVE = LivenessResult(LivenessStatus.PASS, 0.05)
LOW_DF = DeepfakeResult(0.05, "LOW")


def decide(**kw):
    base = dict(document_status="VALID", document_risk=0.05, face_status=FaceMatch.MATCH, capture_issue=None,
                liveness=PASS_LIVE, deepfake=LOW_DF, extra_tamper_flags=[], similarity=0.6)
    base.update(kw)
    return decide_identity(**base)


def test_all_layers_pass_is_verified():
    d = decide()
    assert d.status == KycStatus.VERIFIED and d.legacy_decision == VerificationStatus.APPROVED


@pytest.mark.parametrize("kw,expected", [
    (dict(document_status="VERIFICATION_UNAVAILABLE"), KycStatus.VERIFICATION_UNAVAILABLE),
    (dict(document_status="MANUAL_REVIEW_REQUIRED"), KycStatus.MANUAL_REVIEW_REQUIRED),
    (dict(document_status=None), KycStatus.MANUAL_REVIEW_REQUIRED),
    (dict(document_status="INVALID"), KycStatus.REJECTED),
    (dict(document_status="SUSPICIOUS"), KycStatus.SUSPICIOUS),
    (dict(face_status=FaceMatch.NO_MATCH, similarity=0.1), KycStatus.REJECTED),           # different person
    (dict(face_status=FaceMatch.UNCERTAIN, similarity=0.27), KycStatus.MANUAL_REVIEW_REQUIRED),
    (dict(liveness=LivenessResult(LivenessStatus.FAIL, 0.9, reasons=["screen"])), KycStatus.SUSPICIOUS),   # replay / photo attack
    (dict(liveness=LivenessResult(LivenessStatus.UNCERTAIN, 0.5)), KycStatus.MANUAL_REVIEW_REQUIRED),
    (dict(deepfake=DeepfakeResult(0.9, "HIGH", reasons=["swap"])), KycStatus.SUSPICIOUS),             # face swap
    (dict(deepfake=DeepfakeResult(0.5, "REVIEW")), KycStatus.MANUAL_REVIEW_REQUIRED),
    (dict(face_status=None, capture_issue="No face detected in live capture"), KycStatus.MANUAL_REVIEW_REQUIRED),
    (dict(extra_tamper_flags=["Photo printed on the card does not match the photo in the Aadhaar QR code"]), KycStatus.SUSPICIOUS),
])
def test_decision_matrix(kw, expected):
    d = decide(**kw)
    assert d.status == expected
    assert (d.status == KycStatus.VERIFIED) == (expected == KycStatus.VERIFIED)


def test_document_unavailable_is_never_approved():
    d = decide(document_status="VERIFICATION_UNAVAILABLE")
    assert d.legacy_decision != VerificationStatus.APPROVED and d.reasons


def test_suspicious_outranks_face_mismatch_and_reasons_listed():
    d = decide(face_status=FaceMatch.NO_MATCH, liveness=LivenessResult(LivenessStatus.FAIL, 0.9, reasons=["screen"]))
    assert d.status == KycStatus.SUSPICIOUS and len(d.reasons) >= 2
