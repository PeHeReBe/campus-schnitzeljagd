import os, glob
[os.remove(f) for f in glob.glob('tests/test_data/*.db')]
os.environ['DATA_DIR'] = os.path.join('tests', 'test_data')

from backend.database import init_db
init_db()

from fastapi.testclient import TestClient
from app import app
import base64

c = TestClient(app, raise_server_exceptions=True)
A = 'Basic ' + base64.b64encode(b'admin:campus2026').decode()

st = c.post('/api/admin/stations', json={'name': 'Bib', 'points': 10}, headers={'Authorization': A})
print('station:', st.json())

t = c.post('/api/teams', json={'name': 'T1', 'pin': '1234'})
print('team:', t.json())

l = c.post('/api/teams/login', json={'name': 'T1', 'pin': '1234'})
print('login:', l.json())

team_id = l.json()['id']
code = st.json()['code']
print(f'Scanning: team_id={team_id}, code={code}')

try:
    scan = c.post(f'/api/teams/{team_id}/scan', json={'code': code, 'pin': '1234'})
    print('scan status:', scan.status_code)
    print('scan body:', scan.text)
except Exception as e:
    print('SCAN ERROR:', type(e).__name__, e)
