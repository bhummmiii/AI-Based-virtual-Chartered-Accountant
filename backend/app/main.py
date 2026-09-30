"""
FastAPI Application — Entry Point
AI-Based Chartered Accountant API
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.database.session import engine, Base
from app.middleware.logging_middleware import LoggingMiddleware
from app.api.auth_router import router as auth_router
from app.api.client_router import router as client_router
from app.api.invoice_router import router as invoice_router
from app.api.routers.ocr.router import router as ocr_router
from app.api.routers.gst.router import router as gst_router
from app.api.routers.accounting.router import router as accounting_router
from app.api.routers.tax.router import router as tax_router
from app.api.routers.reports.router import router as reports_router
from app.api.routers.chatbot.router import router as chatbot_router
# Register all 10 models with Base.metadata
import app.models  # noqa: F401

settings = get_settings()

# ── Logging Configuration ────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Application Lifespan ─────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown lifecycle events."""
    logger.info("Starting AI-Based Chartered Accountant API...")
    # Create all tables (development convenience — use Alembic in production)
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")
    yield
    logger.info("Shutting down API...")


# ── FastAPI Application ──────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Production-ready REST API for an AI-Based Chartered Accountant Assistant. "
        "Provides workspace management, client dashboards, accounting, GST, tax, "
        "audit tracking, document management, and reporting."
    ),
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ── Middleware ────────────────────────────────────────────────
# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging
app.add_middleware(LoggingMiddleware)


# ── Health Check ──────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
    }


# ── API Routers ───────────────────────────────────────────────
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(client_router, prefix="/api/v1/clients", tags=["Clients"])
app.include_router(invoice_router, prefix="/api/v1/invoices", tags=["Invoices"])
app.include_router(ocr_router, prefix="/api/v1/ocr", tags=["OCR"])
app.include_router(gst_router, prefix="/api/v1/gst", tags=["GST"])
app.include_router(accounting_router, prefix="/api/v1/accounting", tags=["Accounting"])
app.include_router(tax_router, prefix="/api/v1/tax", tags=["Tax"])
app.include_router(reports_router, prefix="/api/v1/reports", tags=["Reports"])
app.include_router(chatbot_router, prefix="/api/v1/chatbot", tags=["Chatbot"])
