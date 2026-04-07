import secrets
import io
import json
import hashlib
import re
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import Annotated, Optional, List
import os
import qrcode
from fpdf import FPDF

from ..database import get_db
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


class BulkTeamCreate(BaseModel):
    prefix: Optional[str] = "Team"
    count: Optional[int] = 20
    start: Optional[int] = 1


@router.post("/teams/bulk", status_code=201, dependencies=[Depends(require_admin)])
def create_teams_bulk(body: BulkTeamCreate):
    if not body.count or body.count < 1 or body.count > 100:
        raise HTTPException(400, "Anzahl muss zwischen 1 und 100 liegen")
    prefix = (body.prefix or "Team").strip()
    if not prefix:
        raise HTTPException(400, "Prefix benötigt")
    start = body.start if body.start is not None else 1
    db = get_db()
    created = []
    errors = []
    for i in range(start, start + body.count):
        name = f"{prefix} {i}"
        pin = secrets.token_hex(4)
        pin_hash = hashlib.sha256(pin.encode()).hexdigest()
        login_token = secrets.token_urlsafe(24)
        try:
            cur = db.execute(
                "INSERT INTO teams (name, pin, login_token) VALUES (?, ?, ?)",
                (name, pin_hash, login_token)
            )
            db.commit()
            created.append({"id": cur.lastrowid, "name": name, "login_token": login_token})
        except Exception as e:
            if "UNIQUE" in str(e):
                errors.append(f"'{name}' bereits vergeben")
            else:
                errors.append(f"Fehler bei '{name}': {str(e)}")
    return {"created": created, "errors": errors}


# ---- Import ----

class MarkdownImport(BaseModel):
    markdown: str
    default_points: Optional[int] = 10
    question_type: Optional[str] = "text_answer"


@router.post("/import-questions", status_code=201, dependencies=[Depends(require_admin)])
def import_questions(body: MarkdownImport):
    valid_types = ("qr_only", "multiple_choice", "text_answer", "photo_upload")
    qtype = body.question_type if body.question_type in valid_types else "text_answer"
    points = body.default_points if body.default_points and body.default_points > 0 else 10

    # Split on horizontal rules (--- or *** or ___)
    raw_sections = re.split(r'\n\s*[-*_]{3,}\s*\n', body.markdown)

    db = get_db()
    imported = []
    skipped = []

    for idx, section in enumerate(raw_sections):
        section = section.strip()
        if not section:
            continue

        lines = section.splitlines()

        # Extract name and subtitle from headings
        name = None
        subtitle = None
        body_lines = []
        seen_heading = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('### ') and subtitle is None:
                subtitle = stripped[4:].strip()
                seen_heading = True
            elif stripped.startswith('## ') and not stripped.startswith('### ') and name is None:
                name = stripped[3:].strip()
                seen_heading = True
            elif stripped.startswith('# ') and not stripped.startswith('## ') and name is None:
                name = stripped[2:].strip()
                seen_heading = True
            elif seen_heading:
                body_lines.append(line)

        # Skip sections without a ### subtitle – they are typically intro/instructions blocks
        if subtitle is None:
            # Fall back: import if heading looks like a short identifier (≤4 words, no multi-## subheadings)
            multi_section_count = sum(
                1 for l in lines
                if l.strip().startswith('## ') and not l.strip().startswith('### ')
            )
            if multi_section_count >= 2 or name is None:
                skipped.append(f"Abschnitt {idx + 1}: übersprungen (kein Untertitel / Einleitungsblock)")
                continue

        # Use subtitle as name if available (more descriptive), fallback to heading
        display_name = subtitle if subtitle else name
        if not display_name:
            skipped.append(f"Abschnitt {idx + 1}: kein auswertbarer Titel")
            continue

        # Combine number prefix from heading with subtitle for clarity
        if subtitle and name:
            display_name = f"{name}: {subtitle}"

        # Build question text from body
        question_text = "\n".join(body_lines).strip()
        # Remove markdown image references
        question_text = re.sub(r'!\[.*?\]\(.*?\)', '', question_text).strip()

        code = secrets.token_hex(8)
        cur = db.execute(
            """INSERT INTO stations (name, description, lat, lng, code, points, sort_order,
               question_type, question_text, choices, correct_answer) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (display_name, "", None, None, code, points, idx,
             qtype, question_text, "[]", "")
        )
        db.commit()
        imported.append({"id": cur.lastrowid, "name": display_name})

    return {"imported": imported, "skipped": skipped, "count": len(imported)}


# ---- PDF Exports ----

def _make_qr_png_bytes(url: str) -> bytes:
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pdf_safe(text: str) -> str:
    """Remove characters not supported by FPDF built-in fonts (latin-1 range only)."""
    return text.encode("latin-1", errors="ignore").decode("latin-1")


@router.get("/export/stations-qr-pdf", dependencies=[Depends(require_admin)])
def export_stations_qr_pdf(request: Request):
    db = get_db()
    stations = db.execute("SELECT * FROM stations ORDER BY sort_order").fetchall()
    if not stations:
        raise HTTPException(404, "Keine Stationen vorhanden")

    base_url = str(request.base_url).rstrip("/")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)

    # A4 = 210mm wide, 297mm tall
    # Layout: 2 columns, 3 rows per page = 6 QR codes per page
    cols = 2
    margin = 10
    cell_w = (210 - margin * 2) / cols  # ~95mm
    qr_size = 70  # mm
    label_h = 10
    cell_h = qr_size + label_h + 8  # total cell height with padding

    items = list(stations)
    per_page = 6
    pages = (len(items) + per_page - 1) // per_page

    for page_i in range(pages):
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Station QR-Codes", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, "Campus Schnitzeljagd", align="C", new_x="LMARGIN", new_y="NEXT")
        start_y = pdf.get_y() + 4

        for slot in range(per_page):
            idx = page_i * per_page + slot
            if idx >= len(items):
                break
            station = items[idx]
            col = slot % cols
            row = slot // cols
            x = margin + col * cell_w + (cell_w - qr_size) / 2
            y = start_y + row * cell_h

            scan_url = f"{base_url}/scan.html?code={station['code']}"
            qr_bytes = _make_qr_png_bytes(scan_url)

            # Write QR to temp buffer and add to PDF
            buf = io.BytesIO(qr_bytes)
            pdf.image(buf, x=x, y=y, w=qr_size, h=qr_size)

            # Station name label
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_xy(margin + col * cell_w, y + qr_size + 1)
            pdf.cell(cell_w, 5, _pdf_safe(station['name']), align="C", new_x="RIGHT", new_y="TOP")

            # Station points/type label
            pdf.set_font("Helvetica", "", 8)
            pdf.set_xy(margin + col * cell_w, y + qr_size + 6)
            pdf.cell(cell_w, 4, f"{station['points']} Punkte - {station['question_type']}", align="C")

    pdf_bytes = pdf.output()
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=station-qr-codes.pdf"}
    )


@router.get("/export/teams-qr-pdf", dependencies=[Depends(require_admin)])
def export_teams_qr_pdf(request: Request):
    db = get_db()
    teams = db.execute("SELECT * FROM teams ORDER BY id").fetchall()
    if not teams:
        raise HTTPException(404, "Keine Teams vorhanden")

    base_url = str(request.base_url).rstrip("/")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)

    cols = 2
    margin = 10
    cell_w = (210 - margin * 2) / cols
    qr_size = 70
    label_h = 10
    cell_h = qr_size + label_h + 8

    items = list(teams)
    per_page = 6
    pages = (len(items) + per_page - 1) // per_page

    for page_i in range(pages):
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "Team Login QR-Codes", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, "Campus Schnitzeljagd - zum Ausdrucken und Verteilen", align="C", new_x="LMARGIN", new_y="NEXT")
        start_y = pdf.get_y() + 4

        for slot in range(per_page):
            idx = page_i * per_page + slot
            if idx >= len(items):
                break
            team = items[idx]
            col = slot % cols
            row = slot // cols
            x = margin + col * cell_w + (cell_w - qr_size) / 2
            y = start_y + row * cell_h

            join_url = f"{base_url}/join.html?token={team['login_token']}"
            qr_bytes = _make_qr_png_bytes(join_url)

            buf = io.BytesIO(qr_bytes)
            pdf.image(buf, x=x, y=y, w=qr_size, h=qr_size)

            pdf.set_font("Helvetica", "B", 10)
            pdf.set_xy(margin + col * cell_w, y + qr_size + 1)
            pdf.cell(cell_w, 5, _pdf_safe(team['name']), align="C", new_x="RIGHT", new_y="TOP")

            pdf.set_font("Helvetica", "", 8)
            pdf.set_xy(margin + col * cell_w, y + qr_size + 7)
            pdf.cell(cell_w, 4, "Scanne zum Einloggen", align="C")

    pdf_bytes = pdf.output()
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=team-qr-codes.pdf"}
    )


@router.get("/export/questions-pdf", dependencies=[Depends(require_admin)])
def export_questions_pdf():
    db = get_db()
    stations = db.execute("SELECT * FROM stations ORDER BY sort_order").fetchall()

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    margin = 15

    QTYPE_LABELS = {
        "qr_only": "Nur QR-Code",
        "multiple_choice": "Multiple Choice",
        "text_answer": "Text-Antwort",
        "photo_upload": "Foto-Upload",
    }

    # ---- Title Page ----
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 24)
    pdf.ln(30)
    pdf.cell(0, 12, "Campus Schnitzeljagd", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 16)
    pdf.cell(0, 10, "Fragen & Spielanleitung", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Anzahl Stationen: {len(stations)}", align="C", new_x="LMARGIN", new_y="NEXT")

    # ---- Instructions Page ----
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Spielanleitung", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    instructions = [
        ("Ziel des Spiels",
         "Findet alle versteckten QR-Codes auf dem Campus und beantwortet die Fragen an den Stationen. "
         "Das Team mit den meisten Punkten gewinnt!"),
        ("QR-Code scannen",
         "Scannt den QR-Code an jeder Station mit eurer Kamera oder dem QR-Code-Scanner eures Geraets. "
         "Ihr werdet automatisch zur Frage weitergeleitet."),
        ("Fragen beantworten",
         "Je nach Stationstyp muesst ihr: eine Multiple-Choice-Frage beantworten, eine Freitextantwort eingeben, "
         "ein Foto hochladen oder einfach den QR-Code scannen."),
        ("Punkte sammeln",
         "Fuer jede richtige/genehmigte Antwort erhaltet ihr Punkte. "
         "Richtige Multiple-Choice-Antworten werden sofort genehmigt. "
         "Text- und Fotoantworten muessen vom Admin genehmigt werden."),
        ("Rangliste",
         "Die aktuelle Rangliste ist jederzeit auf der Startseite sichtbar. "
         "Punkte werden in Echtzeit aktualisiert."),
        ("Hinweise fuer Helfer",
         "Stellt sicher, dass alle QR-Codes gut sichtbar und erreichbar angebracht sind. "
         "Behaltet die ausstehenden Antworten im Admin-Panel im Blick und genehmigt oder lehnt sie zeitnah ab."),
    ]

    for title, text in instructions:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, text)
        pdf.ln(3)

    # ---- Questions Pages ----
    if stations:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Stationen und Fragen", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        for i, station in enumerate(stations):
            # Check if we need a new page (rough estimate)
            if pdf.get_y() > 250:
                pdf.add_page()

            qtype_label = QTYPE_LABELS.get(station['question_type'], station['question_type'])

            # Station header
            pdf.set_font("Helvetica", "B", 12)
            header = _pdf_safe(f"Station {i + 1}: {station['name']}")
            pdf.cell(0, 8, header, new_x="LMARGIN", new_y="NEXT")

            # Meta info
            pdf.set_font("Helvetica", "", 9)
            meta = f"Typ: {qtype_label}   |   Punkte: {station['points']}"
            pdf.cell(0, 5, meta, new_x="LMARGIN", new_y="NEXT")

            # Description
            if station['description']:
                pdf.set_font("Helvetica", "I", 10)
                pdf.multi_cell(0, 5, _pdf_safe(station['description']))

            # Question text
            if station['question_text']:
                pdf.set_font("Helvetica", "", 10)
                pdf.multi_cell(0, 6, _pdf_safe(station['question_text']))

            # Multiple choice options
            if station['question_type'] == 'multiple_choice' and station['choices']:
                try:
                    choices = json.loads(station['choices'])
                    if choices:
                        pdf.set_font("Helvetica", "B", 10)
                        pdf.cell(0, 5, "Antwortmoeglichkeiten:", new_x="LMARGIN", new_y="NEXT")
                        pdf.set_font("Helvetica", "", 10)
                        for j, choice in enumerate(choices):
                            letter = chr(65 + j)  # A, B, C, ...
                            pdf.cell(8, 5, f"{letter})", new_x="RIGHT", new_y="TOP")
                            pdf.multi_cell(0, 5, _pdf_safe(choice))
                except (json.JSONDecodeError, TypeError):
                    pass

            pdf.ln(4)
            # Horizontal divider
            y = pdf.get_y()
            pdf.line(margin, y, 210 - margin, y)
            pdf.ln(3)

    pdf_bytes = pdf.output()
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=fragen-spielanleitung.pdf"}
    )


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
        photo_full = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", scan["photo_path"])
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
