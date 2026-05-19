"""
MongoDB async connection manager using Motor.
All database operations are centralised here so services stay clean.
"""

import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    global _client, _db
    url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB_NAME", "kyc_verification")
    _client = AsyncIOMotorClient(url)
    _db = _client[db_name]
    # Verify connectivity
    await _client.admin.command("ping")
    logger.info("Connected to MongoDB: %s / %s", url, db_name)
    await _ensure_indexes()


async def disconnect_db() -> None:
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB connection closed")


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialised. Call connect_db() first.")
    return _db


# ── Collection helpers ────────────────────────────────────────────────────────

def verifications_col():
    return get_db()["verifications"]


def sessions_col():
    return get_db()["sessions"]


# ── Index creation ─────────────────────────────────────────────────────────────

async def _ensure_indexes() -> None:
    db = get_db()
    await db["verifications"].create_index("session_id")
    await db["verifications"].create_index("created_at")
    await db["verifications"].create_index("final_decision")
    await db["sessions"].create_index("session_id", unique=True)
    logger.info("MongoDB indexes ensured")
