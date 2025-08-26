from __future__ import annotations

import os
import time
import math
import threading
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()

# simplest: auto-instrument and expose /metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# IMPORTANT: don't import ray at module import time; import inside helpers/endpoints
# This avoids client import/side-effects crashing module import on boot.

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
APP_NAME = "llamaindex-local-api"
RAY_ADDRESS = os.getenv("RAY_ADDRESS", "ray://ray-head:10001")
_RAW_DB_URL = os.getenv("DATABASE_URL", "postgres://appuser:devpass@postgres:5432/appdb")

# Normalize DB URL to psycopg v3 driver *without* touching the DB yet
def _normalized_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

DATABASE_URL = _normalized_db_url(_RAW_DB_URL)

# -----------------------------------------------------------------------------
# Lazy DB (no connection at import time)
# -----------------------------------------------------------------------------
_engine = None
_SessionLocal = None
_db_lock = threading.Lock()

def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        with _db_lock:
            if _engine is None:
                _engine = create_engine(
                    DATABASE_URL,
                    echo=False,
                    future=True,
                    pool_pre_ping=True,
                )
                _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
                _bootstrap_schema(_engine)
    return _engine

def _bootstrap_schema(engine):
    # Keep bootstrap idempotent
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS notes (
              id SERIAL PRIMARY KEY,
              title TEXT NOT NULL,
              body TEXT
            );
        """))

# -----------------------------------------------------------------------------
# Lazy Ray client (initialize only when an endpoint needs it)
# -----------------------------------------------------------------------------
_ray_lock = threading.Lock()
_ray_inited = False

def _ensure_ray():
    """
    Import Ray only when needed; connect (or reconnect) to the head.
    """
    global _ray_inited
    import ray  # local import to avoid import-time side effects

    with _ray_lock:
        try:
            if not _ray_inited or not ray.is_initialized():
                ray.init(address=RAY_ADDRESS, namespace=APP_NAME)
                _ray_inited = True
            # quick no-op to validate session
            @ray.remote
            def _noop() -> bool:
                return True
            ray.get(_noop.remote(), timeout=5)
        except Exception:
            # hard reset once
            try:
                ray.shutdown()
            except Exception:
                pass
            time.sleep(0.3)
            ray.init(address=RAY_ADDRESS, namespace=APP_NAME)
            @ray.remote
            def _noop2() -> bool:
                return True
            ray.get(_noop2.remote(), timeout=5)

# -----------------------------------------------------------------------------
# Ray tasks (defined as callables that create @ray.remote inside the call)
# This avoids referencing ray at module import time.
# -----------------------------------------------------------------------------
def _square_remote():
    import ray
    @ray.remote
    def square(x: float) -> float:
        return x * x
    return square

def _cosine_remote():
    import ray
    @ray.remote
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        if len(a) != len(b):
            raise ValueError("Vectors must have same length")
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0
    return cosine_similarity

# -----------------------------------------------------------------------------
# API models
# -----------------------------------------------------------------------------
class NoteIn(BaseModel):
    title: str
    body: Optional[str] = None

class NoteOut(NoteIn):
    id: int

# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------
app = FastAPI(title="LlamaIndex Dev API", version="0.3.0")

@app.get("/health")
def health():
    return {"ok": True, "service": APP_NAME}

@app.get("/info")
def info():
    # No DB connect here; just show config introspection
    return {"ok": True, "ray_address": RAY_ADDRESS, "db_driver": DATABASE_URL.split("://", 1)[0]}

@app.get("/db/ping")
def db_ping():
    try:
        eng = get_engine()
        with eng.connect() as conn:
            val = conn.execute(text("SELECT 1")).scalar_one()
        return {"ok": True, "result": int(val)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

@app.post("/notes", response_model=NoteOut)
def create_note(note: NoteIn):
    try:
        eng = get_engine()
        with eng.begin() as conn:
            new_id = conn.execute(
                text("INSERT INTO notes(title, body) VALUES (:t, :b) RETURNING id"),
                {"t": note.title, "b": note.body},
            ).scalar_one()
        return NoteOut(id=new_id, **note.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

@app.get("/notes", response_model=List[NoteOut])
def list_notes():
    try:
        eng = get_engine()
        with eng.connect() as conn:
            rows = conn.execute(text("SELECT id, title, body FROM notes ORDER BY id DESC")).all()
        return [NoteOut(id=r.id, title=r.title, body=r.body) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

@app.get("/ray/ping")
def ray_ping():
    try:
        _ensure_ray()
        import ray
        square = _square_remote()
        return {"ok": True, "square(9)": ray.get(square.remote(9))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ray error: {e}")

@app.get("/ray/cosine")
def ray_cosine(a: str, b: str):
    try:
        _ensure_ray()
        import ray
        va = [float(x) for x in a.split(",")]
        vb = [float(x) for x in b.split(",")]
        cosine = _cosine_remote()
        return {"ok": True, "cosine": ray.get(cosine.remote(va, vb))}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ray error: {e}")

Instrumentator().instrument(app).expose(app)
