import os
import logging
import time
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import Request
from contextlib import asynccontextmanager

from backend.database import init_db, DATA_DIR
from backend.ws import ws_endpoint
from backend.routes.teams_api import router as teams_router
from backend.routes.stations_api import router as stations_router
from backend.routes.admin_api import router as admin_router

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend", "dist")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
access_logger = logging.getLogger("campus_hunt.access")
DEFAULT_TRUSTED_PROXY_IPS = "134.169.82.149"
TRUSTED_PROXY_IPS = {
    ip.strip() for ip in os.environ.get("TRUSTED_PROXY_IPS", DEFAULT_TRUSTED_PROXY_IPS).split(",") if ip.strip()
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Campus Schnitzeljagd", lifespan=lifespan)

# API routes
app.include_router(teams_router)
app.include_router(stations_router)
app.include_router(admin_router)


def _get_client_ip(request: Request) -> str:
    direct_ip = request.client.host if request.client else "-"
    trust_proxy_headers = "*" in TRUSTED_PROXY_IPS or direct_ip in TRUSTED_PROXY_IPS

    if not trust_proxy_headers:
        return direct_ip

    x_forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    x_real_ip = request.headers.get("x-real-ip", "").strip()
    if x_real_ip:
        return x_real_ip

    return direct_ip


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    client_ip = _get_client_ip(request)
    method = request.method
    path = request.url.path

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        access_logger.exception('%s "%s %s" 500 %.2fms', client_ip, method, path, duration_ms)
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    access_logger.info('%s "%s %s" %s %.2fms', client_ip, method, path, response.status_code, duration_ms)
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}


# WebSocket
app.websocket("/ws")(ws_endpoint)

# Serve uploaded files
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Static frontend files
app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")


@app.get("/scan.html")
async def scan_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "scan.html"))


@app.get("/join.html")
async def join_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "join.html"))


@app.get("/admin.html")
async def admin_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "admin.html"))


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    # Serve uploaded files from backend/data/uploads
    if full_path.startswith("uploads/"):
        upload_path = os.path.join(UPLOADS_DIR, full_path[8:])
        if os.path.isfile(upload_path):
            return FileResponse(upload_path)
    file_path = os.path.join(FRONTEND_DIR, full_path)
    if full_path and os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    trusted_proxy_ips = os.environ.get("TRUSTED_PROXY_IPS", DEFAULT_TRUSTED_PROXY_IPS)
    print(f"Campus Hunt läuft auf http://localhost:{port}")
    print(f"Admin: http://localhost:{port}/admin.html (admin / campus2026)")
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips=trusted_proxy_ips)
