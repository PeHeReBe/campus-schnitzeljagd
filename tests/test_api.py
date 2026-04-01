import unittest
import os
import sys
import base64

# Set test data dir before importing
os.environ["DATA_DIR"] = os.path.join(os.path.dirname(__file__), "test_data")
os.makedirs(os.environ["DATA_DIR"], exist_ok=True)

# Remove test db if exists
db_path = os.path.join(os.environ["DATA_DIR"], "hunt.db")
if os.path.exists(db_path):
    os.remove(db_path)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend.database import init_db
init_db()

from fastapi.testclient import TestClient
from app import app

client = TestClient(app, raise_server_exceptions=False)
ADMIN_AUTH = base64.b64encode(b"admin:campus2026").decode()


class TestCampusHunt(unittest.TestCase):
    """All tests in one class to ensure ordering."""

    station_id = None
    station_code = None
    team_id = None
    team_token = None

    def test_01_health(self):
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_02_create_station(self):
        r = client.post("/api/admin/stations", json={
            "name": "Bibliothek", "description": "Alte Bib", "points": 15
        }, headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertIn("id", data)
        self.assertIn("code", data)
        TestCampusHunt.station_id = data["id"]
        TestCampusHunt.station_code = data["code"]

    def test_03_list_admin_stations(self):
        r = client.get("/api/admin/stations", headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.json()), 1)

    def test_04_reject_unauthenticated(self):
        r = client.get("/api/admin/stations")
        self.assertIn(r.status_code, [401, 403])

    def test_05_public_hides_code(self):
        r = client.get("/api/stations")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(len(data), 1)
        self.assertNotIn("code", data[0])

    def test_06_admin_create_team(self):
        """Only admins can create teams now."""
        r = client.post("/api/admin/teams", json={"name": "TestTeam"},
                        headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data["name"], "TestTeam")
        self.assertIn("login_token", data)
        TestCampusHunt.team_token = data["login_token"]

    def test_07_reject_duplicate_team(self):
        r = client.post("/api/admin/teams", json={"name": "TestTeam"},
                        headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 409)

    def test_08_token_login(self):
        """Login via token from QR code."""
        r = client.post("/api/teams/token-login", json={"token": self.team_token})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["name"], "TestTeam")
        self.assertIn("scans", data)
        TestCampusHunt.team_id = data["id"]

    def test_09_reject_invalid_token(self):
        test_input = "invalid_token_xyz"
        r = client.post("/api/teams/token-login", json={"token": test_input})
        self.assertEqual(r.status_code, 401)

    def test_10_team_login_qr(self):
        """Admin can get team login QR code."""
        r = client.get(f"/api/admin/teams/{self.team_id}/qr",
                       headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "image/png")
        self.assertGreater(len(r.content), 100)

    def test_11_scan_station_with_token(self):
        r = client.post(f"/api/teams/{self.team_id}/scan", json={
            "code": self.station_code, "token": self.team_token
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["success"])
        self.assertGreater(r.json()["points"], 0)

    def test_12_reject_duplicate_scan(self):
        r = client.post(f"/api/teams/{self.team_id}/scan", json={
            "code": self.station_code, "token": self.team_token
        })
        self.assertEqual(r.status_code, 409)

    def test_13_reject_invalid_code(self):
        r = client.post(f"/api/teams/{self.team_id}/scan", json={
            "code": "doesnotexist", "token": self.team_token
        })
        self.assertEqual(r.status_code, 404)

    def test_14_leaderboard(self):
        r = client.get("/api/teams")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        team = next((t for t in data if t["name"] == "TestTeam"), None)
        self.assertIsNotNone(team)
        self.assertGreater(team["score"], 0)

    def test_15_stats(self):
        r = client.get("/api/admin/stats", headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(data["teamCount"], 1)
        self.assertGreaterEqual(data["stationCount"], 1)
        self.assertGreaterEqual(data["scanCount"], 1)

    def test_16_qr_png(self):
        r = client.get(
            f"/api/admin/stations/{self.station_id}/qr",
            headers={"Authorization": f"Basic {ADMIN_AUTH}"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "image/png")
        self.assertGreater(len(r.content), 100)

    # ---- Question Type Tests ----

    def test_17_create_mc_station(self):
        r = client.post("/api/admin/stations", json={
            "name": "MC Station", "points": 20,
            "question_type": "multiple_choice",
            "question_text": "Was ist 2+2?",
            "choices": ["3", "4", "5", "6"],
            "correct_answer": "4"
        }, headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 201)
        TestCampusHunt.mc_station_code = r.json()["code"]
        TestCampusHunt.mc_station_id = r.json()["id"]

    def test_18_mc_correct_answer(self):
        """MC with correct answer should be auto-approved."""
        r = client.post(f"/api/teams/{self.team_id}/scan", json={
            "code": self.mc_station_code, "token": self.team_token, "answer": "4"
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["points"], 20)

    def test_19_create_mc_station2(self):
        r = client.post("/api/admin/stations", json={
            "name": "MC Station 2", "points": 10,
            "question_type": "multiple_choice",
            "question_text": "Hauptstadt von DE?",
            "choices": ["München", "Berlin", "Hamburg"],
            "correct_answer": "Berlin"
        }, headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 201)
        TestCampusHunt.mc2_code = r.json()["code"]

    def test_20_mc_wrong_answer(self):
        """MC with wrong answer should be auto-rejected."""
        r = client.post(f"/api/teams/{self.team_id}/scan", json={
            "code": self.mc2_code, "token": self.team_token, "answer": "München"
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "rejected")
        self.assertEqual(data["points"], 0)

    def test_21_create_text_station(self):
        r = client.post("/api/admin/stations", json={
            "name": "Text Station", "points": 15,
            "question_type": "text_answer",
            "question_text": "Beschreibe den Campus."
        }, headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 201)
        TestCampusHunt.text_station_code = r.json()["code"]

    def test_22_text_answer_pending(self):
        """Text answer should be pending until admin approval."""
        r = client.post(f"/api/teams/{self.team_id}/scan", json={
            "code": self.text_station_code, "token": self.team_token, "answer": "Ein schöner Campus"
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "pending")

    def test_23_pending_list(self):
        """Admin should see pending scans."""
        r = client.get("/api/admin/pending", headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(len(data), 1)
        pending = [p for p in data if p["station_name"] == "Text Station"]
        self.assertEqual(len(pending), 1)
        TestCampusHunt.pending_scan_id = pending[0]["id"]

    def test_24_approve_scan(self):
        """Admin approves a pending scan."""
        r = client.put(f"/api/admin/scans/{self.pending_scan_id}/approve", json={
            "status": "approved"
        }, headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["success"])

    def test_25_approved_in_leaderboard(self):
        """After approval, points should show in leaderboard."""
        r = client.get("/api/teams")
        self.assertEqual(r.status_code, 200)
        team = next(t for t in r.json() if t["name"] == "TestTeam")
        # Original 15 (Bibliothek) + 20 (MC correct) + 15 (Text approved) = 50
        self.assertEqual(team["score"], 50)

    def test_26_station_by_code(self):
        """Public endpoint to look up station info by code (without revealing correct answer)."""
        r = client.get(f"/api/stations/by-code/{self.mc_station_code}")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["question_type"], "multiple_choice")
        self.assertEqual(data["question_text"], "Was ist 2+2?")
        self.assertIn("4", data["choices"])
        self.assertNotIn("correct_answer", data)
        self.assertNotIn("code", data)

    def test_27_create_photo_station(self):
        r = client.post("/api/admin/stations", json={
            "name": "Photo Station", "points": 25,
            "question_type": "photo_upload",
            "question_text": "Mache ein Foto vom Eingang."
        }, headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 201)
        TestCampusHunt.photo_station_code = r.json()["code"]

    def test_28_mc_missing_answer(self):
        """MC scan without answer should fail."""
        # Create another MC station for this test
        r = client.post("/api/admin/stations", json={
            "name": "MC NoAns", "points": 5,
            "question_type": "multiple_choice",
            "question_text": "Test?",
            "choices": ["A", "B"],
            "correct_answer": "A"
        }, headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        code = r.json()["code"]
        r = client.post(f"/api/teams/{self.team_id}/scan", json={
            "code": code, "token": self.team_token
        })
        self.assertEqual(r.status_code, 400)

    def test_29_stats_with_pending(self):
        """Stats should reflect pending count."""
        r = client.get("/api/admin/stats", headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("pendingCount", data)

    def test_30_token_login_shows_scan_status(self):
        """Token login response should include scan status."""
        r = client.post("/api/teams/token-login", json={"token": self.team_token})
        self.assertEqual(r.status_code, 200)
        scans = r.json()["scans"]
        statuses = {s["station_name"]: s["status"] for s in scans}
        self.assertEqual(statuses["Bibliothek"], "approved")
        self.assertEqual(statuses["MC Station"], "approved")
        self.assertEqual(statuses["Text Station"], "approved")
        self.assertEqual(statuses["MC Station 2"], "rejected")

    # ---- Scan Management & Admin Log Tests ----

    def test_31_list_all_scans(self):
        """Admin can see all scans."""
        r = client.get("/api/admin/scans", headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(len(data), 4)
        # Each scan has team_name and station_name
        self.assertIn("team_name", data[0])
        self.assertIn("station_name", data[0])
        self.assertIn("status", data[0])

    def test_32_admin_log_has_approve_entry(self):
        """Admin log should contain the approve action from test_24."""
        r = client.get("/api/admin/log", headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(len(data), 1)
        # Should have logged the approval
        approve_logs = [l for l in data if l["action"] == "approved"]
        self.assertGreaterEqual(len(approve_logs), 1)

    def test_33_delete_scan_and_log(self):
        """Admin deletes a scan; team can re-answer; action is logged."""
        # Get the rejected MC Station 2 scan
        r = client.get("/api/admin/scans", headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        scans = r.json()
        mc2_scan = next(s for s in scans if s["station_name"] == "MC Station 2")
        scan_id = mc2_scan["id"]

        # Delete the scan
        r = client.delete(f"/api/admin/scans/{scan_id}", headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["success"])

        # Verify it's gone
        r = client.get("/api/admin/scans", headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        ids = [s["id"] for s in r.json()]
        self.assertNotIn(scan_id, ids)

        # Check admin log
        r = client.get("/api/admin/log", headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        delete_logs = [l for l in r.json() if l["action"] == "delete" and l["target_id"] == scan_id]
        self.assertEqual(len(delete_logs), 1)
        self.assertIn("MC Station 2", delete_logs[0]["details"])

    def test_34_team_can_rescan_after_delete(self):
        """After admin deletes the scan, team can re-answer the station."""
        r = client.post(f"/api/teams/{self.team_id}/scan", json={
            "code": self.mc2_code, "token": self.team_token, "answer": "Berlin"
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "approved")

    def test_35_delete_nonexistent_scan(self):
        """Deleting a scan that doesn't exist returns 404."""
        r = client.delete("/api/admin/scans/99999", headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 404)

    def test_36_final_leaderboard(self):
        """Leaderboard reflects corrected score after re-scan."""
        r = client.get("/api/teams")
        team = next(t for t in r.json() if t["name"] == "TestTeam")
        # 15 (Bibliothek) + 20 (MC correct) + 15 (Text approved) + 10 (MC2 re-done correct) = 60
        self.assertEqual(team["score"], 60)

    def test_37_admin_teams_list_has_token(self):
        """Admin team list includes login_token."""
        r = client.get("/api/admin/teams", headers={"Authorization": f"Basic {ADMIN_AUTH}"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        team = next(t for t in data if t["name"] == "TestTeam")
        self.assertIn("login_token", team)
        self.assertEqual(team["login_token"], self.team_token)

    def test_38_no_public_team_creation(self):
        """Public POST /api/teams should not exist (405 or 422)."""
        r = client.post("/api/teams", json={"name": "Hacker", "pin": "1234"})
        self.assertIn(r.status_code, [404, 405, 422])


if __name__ == "__main__":
    unittest.main()
