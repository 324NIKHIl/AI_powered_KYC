import io

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import HTTPException
from PIL import Image

from utils.uploads import validate_upload


def jpeg_bytes(w=300, h=200):
    return cv2.imencode(".jpg", np.random.default_rng(0).integers(0, 255, (h, w, 3), dtype=np.uint8))[1].tobytes()


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    return buf.getvalue()


def test_valid_uploads_identified_by_content():
    assert validate_upload(jpeg_bytes(), "text/plain").extension == "jpg"       # declared type is ignored
    assert validate_upload(png_bytes(), None).extension == "png"
    assert validate_upload(b"%PDF-1.7 ...", "application/pdf").safe_filename == "upload.pdf"


@pytest.mark.parametrize("payload,code", [
    (b"", 422),
    (b"<?php system($_GET['c']); ?>", 415),
    (b"MZ\x90\x00 executable", 415),
    (b"\xff\xd8\xff garbage that is not a real jpeg", 422),
])
def test_rejects_non_documents(payload, code):
    with pytest.raises(HTTPException) as e:
        validate_upload(payload, "image/jpeg")                                  # lying Content-Type
    assert e.value.status_code == code


def test_size_limit_is_enforced(monkeypatch):
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "1")
    with pytest.raises(HTTPException) as e:
        validate_upload(b"\xff\xd8\xff" + b"0" * (1024 * 1024 + 1), "image/jpeg")
    assert e.value.status_code == 413


def test_decompression_bomb_dimensions_rejected():
    buf = io.BytesIO()
    Image.new("1", (9000, 9000)).save(buf, "PNG")                                # tiny file, 81 MP
    with pytest.raises(HTTPException) as e:
        validate_upload(buf.getvalue(), "image/png")
    assert e.value.status_code == 413


def test_upload_route_rejects_spoofed_file_before_processing():
    from api.routes import document
    app = FastAPI()
    app.include_router(document.router, prefix="/api")
    client = TestClient(app)
    r = client.post("/api/upload-document", files={"file": ("id.jpg", b"<script>alert(1)</script>", "image/jpeg")})
    assert r.status_code == 415
    r = client.post("/api/upload-aadhaar-qr", data={"session_id": "s"}, files={"file": ("x.png", b"nope", "image/png")})
    assert r.status_code == 415


def test_face_route_validates_payload():
    from api.routes import face
    app = FastAPI()
    app.include_router(face.router, prefix="/api")
    client = TestClient(app)
    assert client.post("/api/liveness-check", json={}).status_code == 400
    assert client.post("/api/liveness-check", json={"frame_base64": "###"}).status_code == 400
    too_many = {"session_id": "s", "live_face_base64": "AAAA", "extra_frames_base64": ["AAAA"] * 9}
    assert client.post("/api/face-verify", json=too_many).status_code == 422
