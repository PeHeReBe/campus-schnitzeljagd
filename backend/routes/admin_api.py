import secrets
import io
import json
import hashlib
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import Annotated, Optional, List
import os
import qrcode
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

from ..database import get_db, DATA_DIR
from ..ws import broadcast_sync

router = APIRouter(prefix="/api/admin", tags=["admin"])
security = HTTPBasic()

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "campus2026")

MSG_STATION_NOT_FOUND = "Station nicht gefunden"


def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != ADMIN_USER or credentials.password != ADMIN_PASS:
        raise HTTPException(403, "Zugriff verweigert")
    return credentials


class StationCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    points: Optional[int] = 10
    sort_order: Optional[int] = 0
    question_type: Optional[str] = "qr_only"  # qr_only, multiple_choice, text_answer, photo_upload
    question_text: Optional[str] = ""
    choices: Optional[List[str]] = []
    correct_answer: Optional[str] = ""


class StationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    points: Optional[int] = None
    sort_order: Optional[int] = None
    question_type: Optional[str] = None
    question_text: Optional[str] = None
    choices: Optional[List[str]] = None
    correct_answer: Optional[str] = None


# ---- Stations ----

@router.get("/stations", dependencies=[Depends(require_admin)])
def list_stations():
    db = get_db()
    rows = db.execute("SELECT * FROM stations ORDER BY sort_order").fetchall()
    return [dict(r) for r in rows]


@router.post("/stations", status_code=201, dependencies=[Depends(require_admin)],
             responses={400: {"description": "Ungültige Anfrage"}})
def create_station(body: StationCreate):
    if not body.name or not body.name.strip():
        raise HTTPException(400, "Stationsname benötigt")
    valid_types = ("qr_only", "multiple_choice", "text_answer", "photo_upload")
    if body.question_type not in valid_types:
        raise HTTPException(400, f"Ungültiger Fragetyp. Erlaubt: {', '.join(valid_types)}")
    if body.question_type == "multiple_choice":
        if not body.choices or len(body.choices) < 2:
            raise HTTPException(400, "Multiple Choice benötigt mindestens 2 Antwortmöglichkeiten")
        if not body.correct_answer:
            raise HTTPException(400, "Richtige Antwort muss angegeben werden")
    code = secrets.token_hex(8)
    db = get_db()
    choices_json = json.dumps(body.choices or [], ensure_ascii=False)
    cur = db.execute(
        """INSERT INTO stations (name, description, lat, lng, code, points, sort_order,
           question_type, question_text, choices, correct_answer) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (body.name.strip(), body.description or "", body.lat, body.lng, code,
         body.points or 10, body.sort_order or 0,
         body.question_type, body.question_text or "", choices_json, body.correct_answer or "")
    )
    db.commit()
    return {"id": cur.lastrowid, "name": body.name.strip(), "code": code}


@router.put("/stations/{station_id}", dependencies=[Depends(require_admin)],
            responses={404: {"description": "Station nicht gefunden"}})
def update_station(station_id: int, body: StationUpdate):
    db = get_db()
    existing = db.execute("SELECT * FROM stations WHERE id = ?", (station_id,)).fetchone()
    if not existing:
        raise HTTPException(404, MSG_STATION_NOT_FOUND)
    choices_val = json.dumps(body.choices, ensure_ascii=False) if body.choices is not None else existing["choices"]
    db.execute(
        """UPDATE stations SET name=?, description=?, lat=?, lng=?, points=?, sort_order=?,
           question_type=?, question_text=?, choices=?, correct_answer=? WHERE id=?""",
        (
            body.name if body.name is not None else existing["name"],
            body.description if body.description is not None else existing["description"],
            body.lat if body.lat is not None else existing["lat"],
            body.lng if body.lng is not None else existing["lng"],
            body.points if body.points is not None else existing["points"],
            body.sort_order if body.sort_order is not None else existing["sort_order"],
            body.question_type if body.question_type is not None else existing["question_type"],
            body.question_text if body.question_text is not None else existing["question_text"],
            choices_val,
            body.correct_answer if body.correct_answer is not None else existing["correct_answer"],
            station_id
        )
    )
    db.commit()
    return {"success": True}


@router.delete("/stations/{station_id}", dependencies=[Depends(require_admin)],
               responses={404: {"description": "Station nicht gefunden"}})
def delete_station(station_id: int):
    db = get_db()
    db.execute("DELETE FROM scans WHERE station_id = ?", (station_id,))
    result = db.execute("DELETE FROM stations WHERE id = ?", (station_id,))
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, MSG_STATION_NOT_FOUND)
    return {"success": True}


@router.get("/stations/{station_id}/qr", dependencies=[Depends(require_admin)],
            responses={404: {"description": "Station nicht gefunden"}})
def station_qr(station_id: int, request: Request, format: str = "png"):
    db = get_db()
    station = db.execute("SELECT * FROM stations WHERE id = ?", (station_id,)).fetchone()
    if not station:
        raise HTTPException(404, MSG_STATION_NOT_FOUND)

    base_url = str(request.base_url).rstrip("/")
    scan_url = f"{base_url}/scan.html?code={station['code']}"

    if format == "svg":
        img = qrcode.make(scan_url, image_factory=qrcode.image.svg.SvgImage)
        buf = io.BytesIO()
        img.save(buf)
        return Response(content=buf.getvalue(), media_type="image/svg+xml")

    img = qrcode.make(scan_url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/stations/qr-pdf", dependencies=[Depends(require_admin)])
def stations_qr_pdf(request: Request):
    """Generate a single PDF containing all station QR codes."""
    db = get_db()
    stations = db.execute("SELECT * FROM stations ORDER BY sort_order").fetchall()
    if not stations:
        raise HTTPException(404, "Keine Stationen vorhanden")

    base_url = str(request.base_url).rstrip("/")
    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    margin = 40
    cols, rows_per_page = 3, 4
    title_h = 40
    usable_w = page_w - 2 * margin
    usable_h = page_h - 2 * margin - title_h
    cell_w = usable_w / cols
    cell_h = usable_h / rows_per_page
    qr_size = min(cell_w - 20, cell_h - 35)
    items_per_page = cols * rows_per_page

    for idx, station in enumerate(stations):
        if idx % items_per_page == 0:
            if idx > 0:
                c.showPage()
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(page_w / 2, page_h - margin - 15, "Stationen QR-Codes")

        pos = idx % items_per_page
        col = pos % cols
        row = pos // cols

        cell_x = margin + col * cell_w
        cell_top = page_h - margin - title_h - row * cell_h
        qr_x = cell_x + (cell_w - qr_size) / 2
        qr_y = cell_top - qr_size - 2

        scan_url = f"{base_url}/scan.html?code={station['code']}"
        qr_img = qrcode.make(scan_url, box_size=10, border=2)
        img_buf = io.BytesIO()
        qr_img.save(img_buf, format="PNG")
        img_buf.seek(0)

        c.drawImage(ImageReader(img_buf), qr_x, qr_y, qr_size, qr_size)
        c.setFont("Helvetica-Bold", 9)
        name_text = (station['name'][:28] + '...') if len(station['name']) > 28 else station['name']
        c.drawCentredString(cell_x + cell_w / 2, qr_y - 11, name_text)
        c.setFont("Helvetica", 7)
        c.drawCentredString(cell_x + cell_w / 2, qr_y - 20, f"{station['points']} Punkte")

    c.save()
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=stationen-qr-codes.pdf"}
    )


# ---- Teams ----

@router.get("/teams", dependencies=[Depends(require_admin)])
def list_teams():
    db = get_db()
    rows = db.execute("""
        SELECT t.id, t.name, t.login_token, t.created_at,
            COALESCE(SUM(CASE WHEN sc.status='approved' THEN s2.points ELSE 0 END), 0) AS score,
            COUNT(CASE WHEN sc.status='approved' THEN sc.id END) AS stations_found
        FROM teams t
        LEFT JOIN scans sc ON sc.team_id = t.id
        LEFT JOIN stations s2 ON s2.id = sc.station_id
        GROUP BY t.id
        ORDER BY score DESC
    """).fetchall()
    return [dict(r) for r in rows]


class AdminTeamCreate(BaseModel):
    name: str


@router.post("/teams", status_code=201, dependencies=[Depends(require_admin)],
             responses={400: {"description": "Teamname benötigt"}, 409: {"description": "Teamname bereits vergeben"}})
def create_team(body: AdminTeamCreate):
    if not body.name or not body.name.strip():
        raise HTTPException(400, "Teamname benötigt")
    db = get_db()
    pin = secrets.token_hex(4)  # 8-char random PIN
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    login_token = secrets.token_urlsafe(24)
    try:
        cur = db.execute(
            "INSERT INTO teams (name, pin, login_token) VALUES (?, ?, ?)",
            (body.name.strip(), pin_hash, login_token)
        )
        db.commit()
        return {"id": cur.lastrowid, "name": body.name.strip(), "login_token": login_token}
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, "Teamname bereits vergeben")
        raise


@router.get("/teams/{team_id}/qr", dependencies=[Depends(require_admin)],
            responses={404: {"description": "Team nicht gefunden"}})
def team_login_qr(team_id: int, request: Request, format: str = "png"):
    db = get_db()
    team = db.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    if not team:
        raise HTTPException(404, "Team nicht gefunden")
    base_url = str(request.base_url).rstrip("/")
    join_url = f"{base_url}/join.html?token={team['login_token']}"
    img = qrcode.make(join_url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/teams/qr-pdf", dependencies=[Depends(require_admin)])
def teams_qr_pdf(request: Request):
    """Generate a single PDF containing all team login QR codes."""
    db = get_db()
    teams = db.execute("SELECT * FROM teams ORDER BY name").fetchall()
    if not teams:
        raise HTTPException(404, "Keine Teams vorhanden")

    base_url = str(request.base_url).rstrip("/")
    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    margin = 40
    cols, rows_per_page = 3, 4
    title_h = 40
    usable_w = page_w - 2 * margin
    usable_h = page_h - 2 * margin - title_h
    cell_w = usable_w / cols
    cell_h = usable_h / rows_per_page
    qr_size = min(cell_w - 20, cell_h - 35)
    items_per_page = cols * rows_per_page

    for idx, team in enumerate(teams):
        if idx % items_per_page == 0:
            if idx > 0:
                c.showPage()
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(page_w / 2, page_h - margin - 15, "Team Login QR-Codes")

        pos = idx % items_per_page
        col = pos % cols
        row = pos // cols

        cell_x = margin + col * cell_w
        cell_top = page_h - margin - title_h - row * cell_h
        qr_x = cell_x + (cell_w - qr_size) / 2
        qr_y = cell_top - qr_size - 2

        join_url = f"{base_url}/join.html?token={team['login_token']}"
        qr_img = qrcode.make(join_url, box_size=10, border=2)
        img_buf = io.BytesIO()
        qr_img.save(img_buf, format="PNG")
        img_buf.seek(0)

        c.drawImage(ImageReader(img_buf), qr_x, qr_y, qr_size, qr_size)
        c.setFont("Helvetica-Bold", 9)
        name_text = (team['name'][:28] + '...') if len(team['name']) > 28 else team['name']
        c.drawCentredString(cell_x + cell_w / 2, qr_y - 11, name_text)

    c.save()
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=teams-qr-codes.pdf"}
    )


@router.delete("/teams/{team_id}", dependencies=[Depends(require_admin)],
               responses={404: {"description": "Team nicht gefunden"}})
def delete_team(team_id: int):
    db = get_db()
    db.execute("DELETE FROM scans WHERE team_id = ?", (team_id,))
    result = db.execute("DELETE FROM teams WHERE id = ?", (team_id,))
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Team nicht gefunden")
    return {"success": True}


# ---- Stats ----

@router.get("/stats", dependencies=[Depends(require_admin)])
def get_stats():
    db = get_db()
    team_count = db.execute("SELECT COUNT(*) AS c FROM teams").fetchone()["c"]
    station_count = db.execute("SELECT COUNT(*) AS c FROM stations").fetchone()["c"]
    scan_count = db.execute("SELECT COUNT(*) AS c FROM scans WHERE status='approved'").fetchone()["c"]
    pending_count = db.execute("SELECT COUNT(*) AS c FROM scans WHERE status='pending'").fetchone()["c"]
    return {"teamCount": team_count, "stationCount": station_count, "scanCount": scan_count, "pendingCount": pending_count}


# ---- Pending Approvals ----

@router.get("/pending", dependencies=[Depends(require_admin)])
def list_pending():
    db = get_db()
    rows = db.execute("""
        SELECT sc.id, sc.team_id, sc.station_id, sc.answer, sc.photo_path, sc.status, sc.scanned_at,
               t.name AS team_name, s.name AS station_name, s.question_type, s.question_text, s.points
        FROM scans sc
        JOIN teams t ON t.id = sc.team_id
        JOIN stations s ON s.id = sc.station_id
        WHERE sc.status = 'pending'
        ORDER BY sc.scanned_at
    """).fetchall()
    return [dict(r) for r in rows]


class ApprovalRequest(BaseModel):
    status: str  # 'approved' or 'rejected'


@router.get("/scans", dependencies=[Depends(require_admin)])
def list_all_scans():
    db = get_db()
    rows = db.execute("""
        SELECT sc.id, sc.team_id, sc.station_id, sc.answer, sc.photo_path, sc.status, sc.scanned_at,
               t.name AS team_name, s.name AS station_name, s.question_type, s.question_text, s.points
        FROM scans sc
        JOIN teams t ON t.id = sc.team_id
        JOIN stations s ON s.id = sc.station_id
        ORDER BY sc.scanned_at DESC
    """).fetchall()
    return [dict(r) for r in rows]


@router.put("/scans/{scan_id}/approve",
            responses={400: {"description": "Ungültiger Status"}, 404: {"description": "Scan nicht gefunden"}})
def approve_scan(scan_id: int, body: ApprovalRequest, credentials: Annotated[HTTPBasicCredentials, Depends(require_admin)]):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(400, "Status muss 'approved' oder 'rejected' sein")
    db = get_db()
    scan = db.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if not scan:
        raise HTTPException(404, "Scan nicht gefunden")
    old_status = scan["status"]
    db.execute("UPDATE scans SET status = ? WHERE id = ?", (body.status, scan_id))
    team = db.execute("SELECT name FROM teams WHERE id = ?", (scan["team_id"],)).fetchone()
    station = db.execute("SELECT name, points FROM stations WHERE id = ?", (scan["station_id"],)).fetchone()
    team_name = team["name"] if team else "?"
    station_name = station["name"] if station else "?"
    db.execute(
        "INSERT INTO admin_log (admin_user, action, target_type, target_id, details) VALUES (?, ?, ?, ?, ?)",
        (credentials.username, body.status, "scan", scan_id,
         f"Scan von '{team_name}' bei '{station_name}' von '{old_status}' auf '{body.status}' gesetzt")
    )
    db.commit()
    if body.status == "approved" and station:
        broadcast_sync({"type": "scan", "team": team_name, "station": station_name, "points": station["points"]})
    return {"success": True}


@router.delete("/scans/{scan_id}",
               responses={404: {"description": "Scan nicht gefunden"}})
def delete_scan(scan_id: int, credentials: Annotated[HTTPBasicCredentials, Depends(require_admin)]):
    db = get_db()
    scan = db.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if not scan:
        raise HTTPException(404, "Scan nicht gefunden")
    team = db.execute("SELECT name FROM teams WHERE id = ?", (scan["team_id"],)).fetchone()
    station = db.execute("SELECT name FROM stations WHERE id = ?", (scan["station_id"],)).fetchone()
    team_name = team["name"] if team else "?"
    station_name = station["name"] if station else "?"
    # Delete uploaded photo if exists
    if scan["photo_path"]:
        photo_full = os.path.join(DATA_DIR, scan["photo_path"])
        if os.path.exists(photo_full):
            os.remove(photo_full)
    db.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
    db.execute(
        "INSERT INTO admin_log (admin_user, action, target_type, target_id, details) VALUES (?, ?, ?, ?, ?)",
        (credentials.username, "delete", "scan", scan_id,
         f"Scan gelöscht: '{team_name}' bei '{station_name}' (Status: {scan['status']}, Antwort: {scan['answer'] or '-'})")
    )
    db.commit()
    return {"success": True}


# ---- Reset ----

@router.post("/reset", dependencies=[Depends(require_admin)])
def reset_data():
    db = get_db()
    db.executescript("DELETE FROM scans; DELETE FROM teams;")
    db.commit()
    broadcast_sync({"type": "reset"})
    return {"success": True}


# ---- Admin Log ----

@router.get("/log", dependencies=[Depends(require_admin)])
def get_admin_log():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM admin_log ORDER BY created_at DESC LIMIT 200"
    ).fetchall()
    return [dict(r) for r in rows]
