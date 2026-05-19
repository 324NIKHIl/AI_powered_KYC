"""
AI-Powered KYC Verification System — FastAPI Entry Point
Phase 1: Document OCR + Face Verification
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

from api.routes import document, face, admin
from database.mongodb import connect_db, disconnect_db

FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
FRONTEND_INDEX = os.path.join(FRONTEND_DIST, "index.html")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await disconnect_db()


app = FastAPI(
    title="AI-Powered KYC Verification System",
    description="Phase 1: Document OCR + Face Verification using EasyOCR, MTCNN, and FaceNet",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files for stored uploads ──────────────────────────────────────────
os.makedirs("uploads/documents", exist_ok=True)
os.makedirs("uploads/faces", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ── Built React frontend ─────────────────────────────────────────────────────
if os.path.isdir(os.path.join(FRONTEND_DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(document.router, prefix="/api", tags=["Document Verification"])
app.include_router(face.router,     prefix="/api", tags=["Face Verification"])
app.include_router(admin.router,    prefix="/api", tags=["Admin"])


@app.get("/", include_in_schema=False)
async def root():
    if os.path.exists(FRONTEND_INDEX):
        return FileResponse(FRONTEND_INDEX)
    return {
        "message": "KYC Verification System API",
        "status": "running",
        "version": "1.0.0",
        "phase": "Phase 1 — Document OCR + Face Verification",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}


@app.get("/{path:path}", include_in_schema=False)
async def serve_frontend(path: str):
    if path.startswith(("api/", "uploads/", "assets/")):
        return {"detail": "Not Found"}
    if os.path.exists(FRONTEND_INDEX):
        return FileResponse(FRONTEND_INDEX)
    return {
        "message": "Frontend build not found. Run `npm run build` inside frontend.",
        "status": "backend running",
    }
