import os, glob
[os.remove(f) for f in glob.glob('tests/test_data/*.db')]
os.environ['DATA_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests', 'test_data')
os.makedirs(os.environ['DATA_DIR'], exist_ok=True)

from backend.database import init_db
init_db()

from fastapi.testclient import TestClient
from app import app
import base64

# Use raise_server_exceptions=True to see actual errors
c = TestClient(app, raise_server_exceptions=True)
A = 'Basic ' + base64.b64encode(b'admin:campus2026').decode()

# Step 1: Create station
st = c.post('/api/admin/stations', json={'name': 'Bib', 'points': 10}, headers={'Authorization': A})
print('station:', st.status_code, st.json())
station_code = st.json()['code']

# Step 2: Register team
t = c.post('/api/teams', json={'name': 'T1', 'pin': '1234'})
print('team:', t.status_code, t.json())

# Step 3: Login
lg = c.post('/api/teams/login', json={'name': 'T1', 'pin': '1234'})
print('login:', lg.status_code, lg.json())
team_id = lg.json()['id']

# Step 4: Scan (this is the one that fails)
print(f'\nScanning with team_id={team_id}, code={station_code}')
try:
    scan = c.post(f'/api/teams/{team_id}/scan', json={'code': station_code, 'pin': '1234'})
    print('scan:', scan.status_code, scan.text)
except Exception as e:
    import traceback
    print('EXCEPTION during scan:')
    traceback.print_exc()
