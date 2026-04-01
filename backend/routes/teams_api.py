from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
import hashlib
import json
import os
import uuid
from ..database import get_db, DATA_DIR
from ..ws import broadcast_sync

UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
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


@router.post("/login")
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


@router.post("/token-login")
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


@router.post("/{team_id}/scan")
def scan_station(team_id: int, body: ScanRequest):
    db = get_db()
    team = _auth_team(db, team_id, pin=body.pin, token=body.token)
    station = db.execute("SELECT * FROM stations WHERE code = ?", (body.code,)).fetchone()
    if not station:
        raise HTTPException(404, "Station nicht gefunden")

    q_type = station["question_type"] or "qr_only"

    # Determine status based on question type
    if q_type == "multiple_choice":
        # Auto-validate: check if answer matches correct_answer
        if not body.answer:
            raise HTTPException(400, "Antwort benötigt")
        correct = station["correct_answer"]
        if body.answer.strip() == correct.strip():
            status = "approved"
        else:
            status = "rejected"
    elif q_type in ("text_answer", "photo_upload"):
        # Needs admin approval
        status = "pending"
    else:
        # qr_only: auto-approved
        status = "approved"

    try:
        db.execute(
            "INSERT INTO scans (team_id, station_id, answer, status) VALUES (?, ?, ?, ?)",
            (team["id"], station["id"], body.answer or "", status)
        )
        db.commit()

        if status == "approved":
            broadcast_sync({"type": "scan", "team": team["name"], "station": station["name"], "points": station["points"]})

        result = {"success": True, "station": station["name"], "points": station["points"], "status": status}
        if q_type == "multiple_choice" and status == "rejected":
            result["message"] = "Falsche Antwort! Keine Punkte."
            result["points"] = 0
        elif status == "pending":
            result["message"] = "Antwort eingereicht! Ein Admin wird sie prüfen."
        return result
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, "Station bereits beantwortet")
        raise


@router.post("/{team_id}/upload")
def upload_photo(team_id: int, pin: str = Form(""), code: str = Form(...), token: str = Form(""), file: UploadFile = File(...)):
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

    # Read and limit file size (max 5 MB)
    content = file.file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "Datei zu groß (max 5 MB)")

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
