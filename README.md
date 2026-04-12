# 🏛️ Campus Schnitzeljagd

Eine QR-Code-basierte Schnitzeljagd für Campus-Events, Orientierungstage oder Teambuilding.
Teams scannen QR-Codes an Stationen, beantworten Rätsel und sammeln Punkte — alles in Echtzeit über den Browser!

---

## Inhaltsverzeichnis

- [Schnellstart](#schnellstart)
- [Admin-Anleitung](#admin-anleitung)
  - [Login](#1-admin-login)
  - [Stationen erstellen](#2-stationen-erstellen)
  - [Teams erstellen](#3-teams-erstellen)
  - [QR-Codes drucken](#4-qr-codes-drucken)
  - [Antworten bewerten](#5-antworten-bewerten)
  - [Statistik & Protokoll](#6-statistik--protokoll)
  - [Spiel zurücksetzen](#7-spiel-zurücksetzen)
- [Spieler-Anleitung](#spieler-anleitung)
- [Fragetypen](#fragetypen)
- [Konfiguration](#konfiguration)
- [Docker](#docker)
- [API-Referenz](#api-referenz)
- [Projektstruktur](#projektstruktur)
- [Entwicklung](#entwicklung)

---

## Schnellstart

### Voraussetzungen

- Python 3.10+ (getestet mit 3.12)

### Installation & Start

```bash
# Abhängigkeiten installieren
pip install -r requirements.txt

# Server starten
python app.py
```

Der Server läuft auf **http://localhost:8080**.

### Standard-Zugangsdaten

| Rolle | URL | Benutzer | Passwort |
|-------|-----|----------|----------|
| **Admin** | http://localhost:8080/admin.html | `admin` | `campus2026` |

> Die Zugangsdaten können über Umgebungsvariablen geändert werden (siehe [Konfiguration](#konfiguration)).

---

## Admin-Anleitung

### 1. Admin-Login

1. Öffne **http://localhost:8080/admin.html** im Browser
2. Gib Benutzername und Passwort ein (Standard: `admin` / `campus2026`)
3. Klicke **Anmelden**

### 2. Stationen erstellen

Im Tab **Stationen**:

1. **Name** eingeben (z.B. "Bibliothek", "Mensa")
2. **Beschreibung** eingeben (optional, wird den Spielern angezeigt)
3. **Punkte** festlegen (Standard: 10)
4. **Fragetyp** wählen:
   - **Nur QR-Code** — Punkte gibt es direkt beim Scannen
   - **Multiple Choice** — Frage mit Antwortmöglichkeiten
   - **Text-Antwort** — Freitext, wird manuell bewertet
   - **Foto-Upload** — Spieler laden ein Foto hoch, wird manuell bewertet
5. Bei **Multiple Choice**: Antwortmöglichkeiten eingeben (eine pro Zeile) + richtige Antwort markieren
6. **Station erstellen** klicken

Das System generiert automatisch einen eindeutigen QR-Code pro Station.

### 3. Teams erstellen

Im Tab **Teams**:

1. **Teamname** eingeben (z.B. "Die Schnellen", "Team Rakete")
2. **Team erstellen** klicken
3. Das System generiert automatisch:
   - Einen Login-Token (für QR-Code-Anmeldung)
   - Eine zufällige PIN (für manuelle Anmeldung)

### 4. QR-Codes drucken

Es gibt zwei Arten von QR-Codes:

#### Stations-QR-Codes (an den Stationen aufhängen)
- Im Tab **Stationen** → bei jeder Station auf **📥 QR** klicken
- QR-Code als PNG herunterladen und ausdrucken
- An der physischen Station anbringen

#### Team-Login-QR-Codes (an Teams verteilen)
- Im Tab **Teams** → bei jedem Team auf **🔗 QR** klicken
- QR-Code als PNG herunterladen und ausdrucken
- Dem jeweiligen Team aushändigen

> **Tipp:** Drucke die Team-QR-Codes auf Kärtchen oder Sticker — jedes Team scannt seinen Code einmalig, danach ist es automatisch angemeldet.

### 5. Antworten bewerten

Antworten von **Text-** und **Foto-Stationen** müssen manuell bewertet werden:

1. Wechsle zum Tab **Ausstehend**
2. Sieh dir die eingereichten Antworten/Fotos an
3. Klicke **✅ Genehmigen** (Punkte werden gutgeschrieben) oder **❌ Ablehnen**

**Multiple-Choice-** und **Nur-QR-**Stationen werden automatisch bewertet.

Im Tab **Antworten** kannst du alle eingereichten Antworten sehen und filtern. Einzelne Antworten können auch gelöscht werden (das Team darf dann nochmal antworten).

### 6. Statistik & Protokoll

- **Statistik**: Übersicht über Anzahl Teams, Stationen, genehmigte und ausstehende Scans
- **Protokoll**: Alle Admin-Aktionen (Genehmigungen, Ablehnungen, Löschungen) mit Zeitstempel

### 7. Spiel zurücksetzen

Im Tab **Teams** ganz unten: **Alle Teams & Scans zurücksetzen**

> ⚠️ Das löscht alle Teams und Antworten! Die Stationen bleiben erhalten.

---

## Spieler-Anleitung

### Schritt 1: Team beitreten

**Per QR-Code (empfohlen):**
1. Scanne den Team-QR-Code, den du vom Veranstalter bekommen hast
2. Du wirst automatisch angemeldet

**Per Browser:**
1. Gehe zu **http://localhost:8080**
2. Klicke auf **Team**
3. Gib Teamname und PIN ein (vom Veranstalter)

### Schritt 2: Stationen finden & scannen

1. Finde eine Station auf dem Campus
2. Scanne den QR-Code an der Station mit deinem Handy
3. Je nach Stationstyp:
   - **Nur QR-Code**: Du bekommst sofort Punkte! ✅
   - **Multiple Choice**: Wähle die richtige Antwort → sofortiges Feedback
   - **Text-Antwort**: Schreibe deine Antwort → wird vom Admin bewertet
   - **Foto-Upload**: Mache ein Foto und lade es hoch → wird vom Admin bewertet

### Schritt 3: Punkte sammeln

- Schau auf der **Rangliste**, wie dein Team im Vergleich steht
- Die Rangliste aktualisiert sich in Echtzeit!

---

## Fragetypen

| Typ | Beschreibung | Bewertung | Beispiel |
|-----|-------------|-----------|---------|
| **Nur QR-Code** | Punkte beim Scannen | Automatisch | "Finde die Skulptur im Park" |
| **Multiple Choice** | Frage mit Auswahlmöglichkeiten | Automatisch | "Wann wurde die Uni gegründet? A) 1900 B) 1950 C) 1970" |
| **Text-Antwort** | Offene Frage | Manuell durch Admin | "Beschreibe was du an der Station siehst" |
| **Foto-Upload** | Spieler laden ein Foto hoch | Manuell durch Admin | "Macht ein Teamfoto vor dem Hauptgebäude" |

### Foto-Upload Einschränkungen

- **Erlaubte Formate**: JPEG, PNG, WebP, GIF
- **Maximale Größe**: 5 MB pro Bild

---

## Konfiguration

Über Umgebungsvariablen:

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `PORT` | `8080` | Port des Servers |
| `ADMIN_USER` | `admin` | Admin-Benutzername |
| `ADMIN_PASS` | `campus2026` | Admin-Passwort |
| `DATA_DIR` | `backend/data` | Pfad für Datenbank & Uploads |

### Beispiel: Andere Zugangsdaten

```bash
# Linux/Mac
ADMIN_USER=dozent ADMIN_PASS=geheim123 python app.py

# Windows PowerShell
$env:ADMIN_USER="dozent"; $env:ADMIN_PASS="geheim123"; python app.py
```

---

## Docker

```bash
# Image bauen
docker build -t campus-hunt .

# Container starten
docker run -d \
  -p 8080:8080 \
  -e ADMIN_PASS=meinPasswort \
  -v campus-data:/data \
  campus-hunt
```

Die Datenbank und Uploads werden im Volume `/data` gespeichert und überleben Container-Neustarts.

### Docker Compose mit GHCR (`latest`)

```bash
# Service starten (Port 8080 und persistentes Named Volume)
docker compose up -d
```

Die `docker-compose.yml` verwendet:
- Image: `ghcr.io/peherebe/campus-schnitzeljagd:latest`
- Port-Mapping: `8080:8080`
- Persistentes Named Volume: `campus_data` → `/data`

### Auto-Update Script

```bash
chmod +x autoupdate.sh
CHECK_INTERVAL_SECONDS=30 ./autoupdate.sh
```

Das Script prüft standardmäßig alle 60 Sekunden (konfigurierbar über `CHECK_INTERVAL_SECONDS`) auf neue `latest`-Images und führt nur bei Änderungen ein `docker compose up -d` für den Service aus.

---

## API-Referenz

### Öffentliche Endpunkte (kein Login nötig)

| Methode | URL | Beschreibung |
|---------|-----|-------------|
| `GET` | `/api/health` | Health-Check (`{"status":"ok"}`) |
| `GET` | `/api/teams` | Rangliste aller Teams |
| `GET` | `/api/stations` | Liste aller Stationen (ohne Lösungen) |
| `GET` | `/api/stations/{id}` | Einzelne Station |
| `GET` | `/api/stations/by-code/{code}` | Station per QR-Code suchen |
| `POST` | `/api/teams/login` | Login mit Name + PIN |
| `POST` | `/api/teams/token-login` | Login mit Token (QR-Code) |
| `POST` | `/api/teams/{id}/scan` | Station scannen & Antwort einreichen |
| `POST` | `/api/teams/{id}/upload` | Foto hochladen (multipart/form-data) |

### Admin-Endpunkte (HTTP Basic Auth erforderlich)

| Methode | URL | Beschreibung |
|---------|-----|-------------|
| `GET` | `/api/admin/stations` | Alle Stationen (inkl. Codes & Lösungen) |
| `POST` | `/api/admin/stations` | Station erstellen |
| `PUT` | `/api/admin/stations/{id}` | Station bearbeiten |
| `DELETE` | `/api/admin/stations/{id}` | Station löschen |
| `GET` | `/api/admin/stations/{id}/qr` | Stations-QR-Code (PNG/SVG) |
| `GET` | `/api/admin/teams` | Alle Teams mit Token & Statistik |
| `POST` | `/api/admin/teams` | Team erstellen |
| `DELETE` | `/api/admin/teams/{id}` | Team löschen |
| `GET` | `/api/admin/teams/{id}/qr` | Team-Login-QR-Code (PNG/SVG) |
| `GET` | `/api/admin/stats` | Spielstatistik |
| `GET` | `/api/admin/pending` | Ausstehende Bewertungen |
| `GET` | `/api/admin/scans` | Alle eingereichten Antworten |
| `PUT` | `/api/admin/scans/{id}/approve` | Antwort genehmigen/ablehnen |
| `DELETE` | `/api/admin/scans/{id}` | Antwort löschen |
| `GET` | `/api/admin/log` | Admin-Protokoll |
| `POST` | `/api/admin/reset` | Alle Teams & Scans löschen |

### WebSocket

```
ws://localhost:8080/ws
```

Empfängt Echtzeit-Events:
- `{"type": "scan", "team": "...", "station": "...", "points": 10}` — Scan genehmigt
- `{"type": "reset"}` — Spiel zurückgesetzt

---

## Projektstruktur

```
├── app.py                          # FastAPI Server & Routing
├── requirements.txt                # Python-Abhängigkeiten
├── Dockerfile                      # Docker-Image
├── LICENSE                         # MIT Lizenz
├── backend/
│   ├── __init__.py
│   ├── database.py                 # SQLite-Datenbank & Schema
│   ├── ws.py                       # WebSocket-Broadcast
│   └── routes/
│       ├── __init__.py
│       ├── admin_api.py            # Admin-Endpunkte
│       ├── stations_api.py         # Öffentliche Stations-Endpunkte
│       └── teams_api.py            # Team-Endpunkte (Login, Scan, Upload)
├── frontend/
│   └── dist/
│       ├── index.html              # Hauptseite (Login, Rangliste, Stationen)
│       ├── scan.html               # Station scannen & Fragen beantworten
│       ├── join.html               # Team per QR-Code beitreten
│       ├── admin.html              # Admin-Panel
│       ├── css/style.css           # Styling
│       └── js/
│           ├── app.js              # Frontend-Logik (Spieler)
│           └── admin.js            # Frontend-Logik (Admin)
└── tests/
    └── test_api.py                 # 38 API-Tests
```

---

## Entwicklung

### Tests ausführen

```bash
python -m unittest tests.test_api -v
```

Alle 38 Tests prüfen: API-Endpunkte, Authentifizierung, Fragetypen, Genehmigungen, Berechtigungen und Rangliste.

### Technologie-Stack

- **Backend**: Python, FastAPI, uvicorn, SQLite (WAL-Modus)
- **Frontend**: Vanilla HTML/CSS/JS (kein Framework)
- **QR-Codes**: qrcode + Pillow
- **Echtzeit**: WebSocket

---

## Lizenz

MIT — siehe [LICENSE](LICENSE)
