from fastapi import APIRouter, HTTPException
import json
from ..database import get_db

router = APIRouter(prefix="/api/stations", tags=["stations"])


def _parse_choices(d):
    try:
        d["choices"] = json.loads(d["choices"]) if d["choices"] else []
    except (json.JSONDecodeError, TypeError):
        d["choices"] = []
    return d


@router.get("")
def list_stations():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, description, lat, lng, points, sort_order, question_type, question_text, choices FROM stations ORDER BY sort_order"
    ).fetchall()
    return [_parse_choices(dict(r)) for r in rows]


@router.get("/by-code/{code}")
def get_station_by_code(code: str):
    db = get_db()
    row = db.execute(
        "SELECT id, name, description, lat, lng, points, sort_order, question_type, question_text, choices FROM stations WHERE code = ?",
        (code,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Station nicht gefunden")
    return _parse_choices(dict(row))


@router.get("/{station_id}")
def get_station(station_id: int):
    db = get_db()
    row = db.execute(
        "SELECT id, name, description, lat, lng, points, sort_order, question_type, question_text, choices FROM stations WHERE id = ?",
        (station_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Station nicht gefunden")
    return _parse_choices(dict(row))
