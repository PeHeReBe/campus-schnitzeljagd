from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Annotated, Optional
import hashlib
import json
import os
import uuid
from ..database import get_db, DATA_DIR
from ..ws import broadcast_sync

UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024
os.makedirs(UPLOADS_DIR, exist_ok=True)

router = APIRouter(prefix="/api/teams", tags=["teams"])


class TeamLogin(BaseModel):
    name: str
    pin: str


class TokenLogin(BaseModel):
    token: str


class ScanRequest(BaseModel):
    code: str
    pin: Optional[str] = ""
    token: Optional[str] = ""
    answer: Optional[str] = ""


def _hash(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def _auth_team(db, team_id: int, pin: str = "", token: str = ""):
    """Authenticate a team by either PIN or login_token."""
    if token:
        team = db.execute("SELECT id, name FROM teams WHERE id = ? AND login_token = ?", (team_id, token)).fetchone()
        if team:
            return team
    if pin:
        pin_hash = _hash(pin)
        team = db.execute("SELECT id, name FROM teams WHERE id = ? AND pin = ?", (team_id, pin_hash)).fetchone()
        if team:
            return team
    raise HTTPException(401, "Ungültige Team-Anmeldedaten")


@router.get("")
def list_teams():
    db = get_db()
    rows = db.execute("""
        SELECT t.id, t.name, t.created_at,
            COALESCE(SUM(CASE WHEN sc.status='approved' THEN s2.points ELSE 0 END), 0) AS score,
            COUNT(CASE WHEN sc.status='approved' THEN sc.id END) AS stations_found
        FROM teams t
        LEFT JOIN scans sc ON sc.team_id = t.id
        LEFT JOIN stations s2 ON s2.id = sc.station_id
        GROUP BY t.id
        ORDER BY score DESC
    """).fetchall()
    return [dict(r) for r in rows]


@router.post("/login", responses={401: {"description": "Ungültige Anmeldedaten"}})
def login_team(body: TeamLogin):
    db = get_db()
    pin_hash = _hash(body.pin)
    team = db.execute("SELECT id, name, login_token FROM teams WHERE name = ? AND pin = ?", (body.name, pin_hash)).fetchone()
    if not team:
        raise HTTPException(401, "Ungültige Anmeldedaten")
    scans = db.execute("""
        SELECT s.id AS station_id, s.name AS station_name, s.points, sc.scanned_at, sc.status
        FROM scans sc JOIN stations s ON s.id = sc.station_id
        WHERE sc.team_id = ? ORDER BY sc.scanned_at
    """, (team["id"],)).fetchall()
    return {**dict(team), "scans": [dict(s) for s in scans]}


@router.post("/token-login",
             responses={400: {"description": "Token benötigt"}, 401: {"description": "Ungültiger Token"}})
def token_login(body: TokenLogin):
    """Login via login_token (from QR code scan)."""
    if not body.token:
        raise HTTPException(400, "Token benötigt")
    db = get_db()
    team = db.execute("SELECT id, name, login_token FROM teams WHERE login_token = ?", (body.token,)).fetchone()
    if not team:
        raise HTTPException(401, "Ungültiger Token")
    scans = db.execute("""
        SELECT s.id AS station_id, s.name AS station_name, s.points, sc.scanned_at, sc.status
        FROM scans sc JOIN stations s ON s.id = sc.station_id
        WHERE sc.team_id = ? ORDER BY sc.scanned_at
    """, (team["id"],)).fetchall()
    return {**dict(team), "scans": [dict(s) for s in scans]}


def _determine_scan_status(station, answer: str) -> tuple:
    """Determine scan status and message based on question type."""
    q_type = station["question_type"] or "qr_only"
    if q_type == "multiple_choice":
        if not answer:
            raise HTTPException(400, "Antwort benötigt")
        correct = station["correct_answer"]
        if answer.strip() == (correct or "").strip():
            return "approved", None
        return "rejected", "Falsche Antwort! Keine Punkte."
    if q_type in ("text_answer", "photo_upload"):
        return "pending", "Antwort eingereicht! Ein Admin wird sie prüfen."
    return "approved", None


@router.post("/{team_id}/scan",
             responses={400: {"description": "Ungültige Anfrage"}, 401: {"description": "Ungültige Team-Anmeldedaten"},
                        404: {"description": "Station nicht gefunden"}, 409: {"description": "Station bereits beantwortet"}})
def scan_station(team_id: int, body: ScanRequest):
    db = get_db()
    team = _auth_team(db, team_id, pin=body.pin, token=body.token)
    station = db.execute("SELECT * FROM stations WHERE code = ?", (body.code,)).fetchone()
    if not station:
        raise HTTPException(404, "Station nicht gefunden")

    status, message = _determine_scan_status(station, body.answer or "")

    try:
        db.execute(
            "INSERT INTO scans (team_id, station_id, answer, status) VALUES (?, ?, ?, ?)",
            (team["id"], station["id"], body.answer or "", status)
        )
        db.commit()

        if status == "approved":
            broadcast_sync({"type": "scan", "team": team["name"], "station": station["name"], "points": station["points"]})

        points = 0 if status == "rejected" else station["points"]
        result = {"success": True, "station": station["name"], "points": points, "status": status}
        if message:
            result["message"] = message
        return result
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, "Station bereits beantwortet")
        raise


@router.post("/{team_id}/upload",
             responses={400: {"description": "Ungültige Anfrage"}, 401: {"description": "Ungültige Team-Anmeldedaten"},
                        404: {"description": "Station nicht gefunden"}, 409: {"description": "Station bereits beantwortet"}})
def upload_photo(team_id: int, code: Annotated[str, Form(...)], file: Annotated[UploadFile, File(...)], pin: Annotated[str, Form()] = "", token: Annotated[str, Form()] = ""):
    db = get_db()
    team = _auth_team(db, team_id, pin=pin, token=token)
    station = db.execute("SELECT * FROM stations WHERE code = ?", (code,)).fetchone()
    if not station:
        raise HTTPException(404, "Station nicht gefunden")
    if (station["question_type"] or "qr_only") != "photo_upload":
        raise HTTPException(400, "Station erwartet keinen Foto-Upload")

    # Validate file type
    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if file.content_type not in allowed:
        raise HTTPException(400, "Nur Bilddateien (JPEG, PNG, WebP, GIF) erlaubt")

    # Read and limit file size (max 50 MB)
    content = file.file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(400, "Datei zu groß (max 50 MB)")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        ext = "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOADS_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    try:
        db.execute(
            "INSERT INTO scans (team_id, station_id, answer, photo_path, status) VALUES (?, ?, ?, ?, ?)",
            (team["id"], station["id"], "", f"uploads/{filename}", "pending")
        )
        db.commit()
        return {"success": True, "station": station["name"], "points": station["points"],
                "status": "pending", "message": "Foto hochgeladen! Ein Admin wird es prüfen."}
    except Exception as e:
        # Clean up file if insert fails
        if os.path.exists(filepath):
            os.remove(filepath)
        if "UNIQUE" in str(e):
            raise HTTPException(409, "Station bereits beantwortet")
        raise
