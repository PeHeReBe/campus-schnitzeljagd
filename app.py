import os
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from backend.database import init_db
from backend.ws import ws_endpoint
from backend.routes.teams_api import router as teams_router
from backend.routes.stations_api import router as stations_router
from backend.routes.admin_api import router as admin_router

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend", "dist")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Campus Schnitzeljagd", lifespan=lifespan)

# API routes
app.include_router(teams_router)
app.include_router(stations_router)
app.include_router(admin_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# WebSocket
app.websocket("/ws")(ws_endpoint)

# Serve uploaded files
UPLOADS_DIR = os.path.join(BASE_DIR, "backend", "data", "uploads")
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
    print(f"Campus Hunt läuft auf http://localhost:{port}")
    print(f"Admin: http://localhost:{port}/admin.html (admin / campus2026)")
    uvicorn.run(app, host="0.0.0.0", port=port)
