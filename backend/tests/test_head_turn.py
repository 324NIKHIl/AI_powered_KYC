"""Server-side head-turn challenge: yaw measurement and the pass/fail decision."""

import numpy as np

from services.kyc import challenge as ch


def face(nose_dx):
    """A fake detection: eyes 60px apart, nose shifted by nose_dx px from the eye midpoint."""
    return [{"box": (0, 0, 100, 100), "confidence": 0.99,
             "keypoints": {"left_eye": (70, 50), "right_eye": (130, 50), "nose": (100 + nose_dx, 80)}}]


def frames_for(dxs):
    return [np.full((10, 10, 3), i, np.uint8) for i in range(len(dxs))]


def run(steps, dxs, raw=None):
    it = iter(dxs)
    return ch.verify_challenge(steps, frames_for(dxs), raw_frames=raw or [str(i) for i in range(len(dxs))],
                               detect=lambda _f: face(next(it)))


def test_challenge_is_random_single_use_and_expires():
    seen = {tuple(ch.new_challenge()["steps"]) for _ in range(40)}
    assert seen == {("center", "left", "right"), ("center", "right", "left")}
    c = ch.new_challenge()
    assert ch.check_challenge_usable(c, c["id"]) is None
    assert ch.check_challenge_usable(c, "other") and ch.check_challenge_usable(None, c["id"])
    c["used"] = True
    assert "already used" in ch.check_challenge_usable(c, c["id"])
    c["used"], c["expires_at"] = False, 0
    assert "expired" in ch.check_challenge_usable(c, c["id"])


def test_real_head_turns_pass():
    assert run(["center", "left", "right"], [0, -18, 18]).passed
    assert run(["center", "right", "left"], [2, 20, -16]).passed


def test_static_photo_fails():
    r = run(["center", "left", "right"], [1, 2, 0])      # nose barely moves: a held-up picture
    assert r.status == "FAIL" and len(r.reasons) == 2


def test_wrong_direction_fails():
    assert run(["center", "left", "right"], [0, 18, -18]).status == "FAIL"


def test_identical_frames_fail():
    assert run(["center", "left", "right"], [0, -18, 18], raw=["a", "a", "a"]).status == "FAIL"


def test_missing_face_or_bad_start_is_uncertain_not_fail():
    steps = ["center", "left", "right"]
    r = ch.evaluate(steps, [0.0, None, 0.3])
    assert r.status == "UNCERTAIN"
    assert ch.evaluate(steps, [0.4, -0.2, 0.2]).status == "UNCERTAIN"


def test_wrong_frame_count_fails():
    assert ch.evaluate(["center", "left", "right"], [0.0, -0.3]).status == "FAIL"


async def test_issue_challenge_stores_it_and_hides_nothing_needed(monkeypatch):
    from services import verification_service as vs
    stored = {}

    async def get_session(_sid):
        return {"session_id": "s"}

    async def update_session(_sid, upd):
        stored.update(upd)

    monkeypatch.setattr(vs, "get_session", get_session)
    monkeypatch.setattr(vs, "update_session", update_session)
    view = await vs.issue_liveness_challenge("s")
    assert view["challenge_id"] == stored["liveness_challenge"]["id"]
    assert [s["id"] for s in view["steps"]] == stored["liveness_challenge"]["steps"]
    assert "expires_at" not in view and "used" not in view


async def test_unknown_session_gets_no_challenge(monkeypatch):
    from services import verification_service as vs

    async def get_session(_sid):
        return None

    monkeypatch.setattr(vs, "get_session", get_session)
    assert await vs.issue_liveness_challenge("nope") is None
