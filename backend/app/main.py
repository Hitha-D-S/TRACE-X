"""
TRACE-X FastAPI Application Entry Point
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging_config import configure_logging, get_logger, new_correlation_id
from app.core.security import create_access_token, authenticate_user
from app.db.postgres import create_tables
from app.db.neo4j_client import init_schema, close_driver
from app.db.redis_client import get_redis, close_redis
from app.detection.anomaly import load_model
from app.api.v1 import router as v1_router

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown event handler."""
    logger.info("TRACE-X starting", version=settings.app_version, env=settings.environment)

    # Initialize PostgreSQL tables
    try:
        await create_tables()
        logger.info("PostgreSQL tables ready")
    except Exception as e:
        logger.warning("PostgreSQL init failed — continuing without it", error=str(e))

    # Initialize Neo4j schema
    try:
        await init_schema()
    except Exception as e:
        logger.warning("Neo4j init failed — continuing without it", error=str(e))

    # Load ML model if artifact exists
    model_loaded = load_model()
    if model_loaded:
        logger.info("Anomaly detection model loaded")
    else:
        logger.info("No anomaly model found — ML scoring disabled (rule engine still active)")

    yield  # Application runs here

    # Cleanup
    await close_driver()
    await close_redis()
    logger.info("TRACE-X shut down cleanly")


# ── FastAPI Application ──────────────────────────────────────────
app = FastAPI(
    title="TRACE-X API",
    description=(
        "Real-Time Financial Crime Graph Intelligence. "
        "TRACE-X is an investigator decision-support system. "
        "All data is synthetic. Not for production use."
    ),
    version=settings.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Middleware — correlation ID + timing ─────────────────────────
@app.middleware("http")
async def correlation_timing_middleware(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or new_correlation_id()
    t_start = time.perf_counter()
    response = await call_next(request)
    latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
    response.headers["X-Correlation-ID"] = cid
    response.headers["X-Latency-Ms"] = str(latency_ms)
    return response


# ── Global Exception Handler ─────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=str(request.url), error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please check the logs.", "type": type(exc).__name__},
    )


# ── Auth endpoint ─────────────────────────────────────────────────
from pydantic import BaseModel

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/v1/auth/login", tags=["Auth"])
async def login(req: LoginRequest):
    user = authenticate_user(req.email, req.password)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Invalid credentials"})
    token = create_access_token({"sub": user["email"], "role": user["role"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
        },
    }


# ── Mount API v1 router ──────────────────────────────────────────
app.include_router(v1_router, prefix="/api/v1")


# ── Root ─────────────────────────────────────────────────────────
@app.get("/", tags=["Root"])
async def root() -> Dict[str, Any]:
    return {
        "service": "TRACE-X",
        "tagline": "Real-Time Financial Crime Graph Intelligence",
        "version": settings.app_version,
        "disclaimer": (
            "All data is SYNTHETIC. This is a hackathon demonstration only. "
            "TRACE-X is an investigator decision-support system — it does not "
            "determine criminal liability or make regulatory decisions."
        ),
        "docs": "/api/docs",
    }
