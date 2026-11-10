"""FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload --port 8000
Docs:         http://localhost:8000/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api import analysis, anomalies, compare, custom_datasets, history, reports, synthetic, system, variants
from app.config import get_settings
from app.database import init_db
from app.pipeline.matching import AssemblyMismatchError
from app.services.http import ExternalServiceError
from app.utils import user_message

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("genelens")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.environment != "test":
        from app.sources.status_cache import warm_up

        warm_up()  # source/dataset checks run in the background so the first page load is fast
    log.info("GeneLens API ready – data dir: %s", settings.data_dir)
    yield


app = FastAPI(
    title="GeneLens API",
    version="1.0.0",
    description="Genetic Variant Intelligence Platform – gnomAD × ClinVar research API. "
                "Research use only; not for clinical decision-making.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.exception_handler(ExternalServiceError)
async def external_error(_: Request, exc: ExternalServiceError):
    code = 404 if exc.status_code == 404 else 503
    log.warning("external service error: %s", exc)
    return JSONResponse(status_code=code, content={"detail": user_message(exc), "service": exc.service,
                                                   "type": "external_service_unavailable" if code == 503 else "not_found"})


@app.exception_handler(AssemblyMismatchError)
async def assembly_error(_: Request, exc: AssemblyMismatchError):
    return JSONResponse(status_code=422, content={"detail": str(exc), "type": "assembly_mismatch"})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "; ".join(e["msg"] for e in errors) or "Invalid request",
                                                  "errors": errors, "type": "validation_error"})


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error – see backend logs.",
                                                  "type": "internal_error"})


for r in (system.router, analysis.router, variants.router, anomalies.router, synthetic.router, reports.router,
          history.router, compare.router, custom_datasets.router):
    app.include_router(r, prefix="/api")
