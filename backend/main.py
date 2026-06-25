from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text

from fastapi.exceptions import RequestValidationError

from backend.auth import AuthUser, get_current_user

from backend.api_log_middleware import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from backend.db import SessionLocal
from backend.routes_vendor_file_format import router as vendor_file_format_router
from backend.routes_uploads import router as uploads_router
from backend.routes_store_mapping import router as store_mapping_router
from backend.routes_reconciliation import router as reconciliation_router
from backend.routes_approvals import router as approvals_router
from backend.routes_corrections import router as corrections_router
from backend.routes_pickup_rules import router as pickup_rules_router
from backend.routes_charges import router as charges_router
from backend.routes_month_lock import router as month_lock_router
from backend.routes_reports import router as reports_router
from backend.routes_auth import router as auth_router
from backend.routes_vendor_master import router as vendor_master_router
from backend.routes_bank_store import router as bank_store_router
from backend.routes_charge_config import router as charge_config_router
from backend.routes_vendor_charge import router as vendor_charge_router
from backend.routes_waivers import router as waivers_router
from backend.routes_remittances import router as remittances_router
from backend.routes_customer_charge_slabs import router as customer_charge_slabs_router
from backend.routes_admin import router as admin_router
from backend.routes_finacle_format import router as finacle_format_router
from backend.routes_users import router as users_router
from backend.routes_dashboard import router as dashboard_router

_ENVIRONMENT = os.environ.get("ENVIRONMENT", "").strip().lower()
_IS_PROD_TIER = _ENVIRONMENT in {"uat", "pre", "preprod", "prod", "production", "prd"}
_EXPOSE_DOCS = os.environ.get("EXPOSE_DOCS", "false" if _IS_PROD_TIER else "true").lower() in (
    "true",
    "1",
    "yes",
)

app = FastAPI(
    title="Doorstep Banking Application",
    docs_url="/docs" if _EXPOSE_DOCS else None,
    redoc_url="/redoc" if _EXPOSE_DOCS else None,
    openapi_url="/openapi.json" if _EXPOSE_DOCS else None,
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

_default_cors_origins = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
_env_origins_raw = os.environ.get("CORS_ORIGINS", "").strip()
if _env_origins_raw:
    _cors_origins = [o.strip() for o in _env_origins_raw.split(",") if o.strip() and o.strip() != "*"]
else:
    _cors_origins = _default_cors_origins
logging.getLogger(__name__).info("CORS allow_origins=%s", _cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_CSRF_EXEMPT_PATHS = {
    "/api/auth/login",
}

class SecurityHeadersMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, csp: str, hsts: str | None):
        super().__init__(app)
        self._csp = csp
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next):
        if request.method.upper() not in _CSRF_SAFE_METHODS and request.url.path.startswith("/api/"):
            if request.url.path not in _CSRF_EXEMPT_PATHS:
                has_bearer = (request.headers.get("authorization") or "").lower().startswith("bearer ")
                has_xhr = (request.headers.get("x-requested-with") or "").lower() == "xmlhttprequest"
                has_cookie = bool(request.cookies)
                if has_cookie and not has_bearer and not has_xhr:
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Missing X-Requested-With header"},
                    )

        response = await call_next(request)

        response.headers.setdefault("Content-Security-Policy", self._csp)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if self._hsts:
            response.headers.setdefault("Strict-Transport-Security", self._hsts)
        if "server" in response.headers:
            try:
                del response.headers["server"]
            except KeyError:
                pass
        return response

_DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
_csp_header = os.environ.get("CSP_HEADER", _DEFAULT_CSP)

_hsts_default = "max-age=31536000; includeSubDomains" if _IS_PROD_TIER else ""
_hsts_header = os.environ.get("HSTS_HEADER", _hsts_default).strip() or None

app.add_middleware(SecurityHeadersMiddleware, csp=_csp_header, hsts=_hsts_header)

app.include_router(vendor_file_format_router)
app.include_router(uploads_router)
app.include_router(store_mapping_router)
app.include_router(reconciliation_router)
app.include_router(approvals_router)
app.include_router(corrections_router)
app.include_router(pickup_rules_router)
app.include_router(charges_router)
app.include_router(month_lock_router)
app.include_router(reports_router)
app.include_router(auth_router)
app.include_router(vendor_master_router)
app.include_router(bank_store_router)
app.include_router(charge_config_router)
app.include_router(vendor_charge_router)
app.include_router(waivers_router)
app.include_router(remittances_router)
app.include_router(customer_charge_slabs_router)
app.include_router(admin_router)
app.include_router(finacle_format_router)
app.include_router(users_router)
app.include_router(dashboard_router)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

_HEALTH_DB_INTERNAL_TOKEN = os.environ.get("HEALTH_DB_INTERNAL_TOKEN", "").strip()

@app.get("/api/health/db")
def health_check_db(request: Request):
    if _HEALTH_DB_INTERNAL_TOKEN:
        provided = request.headers.get("X-Internal-Health-Token", "").strip()
        if provided and provided == _HEALTH_DB_INTERNAL_TOKEN:
            return _do_db_health()
    _ = get_current_user(request)
    return _do_db_health()

def _do_db_health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1 FROM dual"))
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        logging.getLogger(__name__).error("DB health check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc
    finally:
        db.close()

_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
