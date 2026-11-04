"""API authorization checks using isolated, temporary SQLite databases."""

import sys
import tempfile
import unittest
import shutil
import uuid
from unittest.mock import patch
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
TEST_DATABASE_DIR = tempfile.TemporaryDirectory(prefix="referee-api-tests-")

from services import database

database.DATABASE_PATH = Path(TEST_DATABASE_DIR.name) / "api.sqlite3"
database._initialized = False

from app import app
from services.auth_service import authenticate
from services.match_pool_service import create_match_pool
from services.referee_service import load_referees

TEST_BASE_DATABASE = Path(TEST_DATABASE_DIR.name) / "base.sqlite3"
with database.connect() as connection:
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
shutil.copy2(database.DATABASE_PATH, TEST_BASE_DATABASE)


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        database.DATABASE_PATH = Path(TEST_DATABASE_DIR.name) / f"{uuid.uuid4().hex}.sqlite3"
        shutil.copy2(TEST_BASE_DATABASE, database.DATABASE_PATH)
        database._initialized = False
        database.initialize_database()
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.csrf_token = None

    def get_csrf_token(self):
        response = self.client.get("/auth/csrf")
        self.assertEqual(response.status_code, 200)
        self.csrf_token = response.get_json()["csrf_token"]
        return self.csrf_token

    def post_json(self, path, payload):
        return self.client.post(
            path,
            json=payload,
            headers={"X-CSRF-Token": self.csrf_token or ""},
        )

    def put_json(self, path, payload):
        return self.client.put(
            path,
            json=payload,
            headers={"X-CSRF-Token": self.csrf_token or ""},
        )

    def login(self, username, password):
        self.get_csrf_token()
        response = self.post_json(
            "/auth/login", {"username": username, "password": password}
        )
        if response.status_code == 200:
            self.csrf_token = response.get_json()["csrf_token"]
        return response

    def change_password(self, current_password, new_password="ChangedPass123"):
        response = self.post_json(
            "/auth/change-password",
            {
                "current_password": current_password,
                "new_password": new_password,
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        return response

    @staticmethod
    def make_match(match_id, match_date):
        return {
            "id": match_id,
            "date": match_date,
            "time": "10:00",
            "age_group": "U-14",
            "location": "Debrecen",
            "home_team": f"Hazai {match_id}",
            "away_team": f"Vendég {match_id}",
            "required_referees": 1,
        }

    def test_login_and_required_first_password_change(self):
        self.assertEqual(self.client.get("/users").status_code, 401)

        self.get_csrf_token()
        response = self.client.post(
            "/auth/login",
            json={"username": "admin", "password": "wrong"},
            headers={"X-CSRF-Token": self.csrf_token},
        )
        self.assertEqual(response.status_code, 401)

        response = self.login("admin", "admin")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["user"]["must_change_password"])
        self.assertEqual(self.client.get("/users").status_code, 403)
        self.assertTrue(
            self.client.get("/auth/me").get_json()["user"]["must_change_password"]
        )

        self.change_password("admin")
        response = self.client.get("/users")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password_hash", response.get_data(as_text=True))

    def test_mutating_requests_require_csrf(self):
        response = self.client.post(
            "/auth/login", json={"username": "admin", "password": "admin"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("CSRF", response.get_json()["error"])

    def test_sender_is_limited_to_owned_uploads_and_sender_permissions(self):
        self.login("admin", "admin")
        self.change_password("admin")
        created = self.post_json(
            "/users", {"username": "sender.one", "role": "sender"}
        )
        self.assertEqual(created.status_code, 201, created.get_json())
        sender_id = next(
            user["user_id"] for user in self.client.get("/users").get_json()["users"]
            if user["username"] == "sender.one"
        )
        other_sender = self.post_json(
            "/users", {"username": "sender.two", "role": "sender"}
        )
        self.assertEqual(other_sender.status_code, 201, other_sender.get_json())
        other_id = next(
            user["user_id"] for user in self.client.get("/users").get_json()["users"]
            if user["username"] == "sender.two"
        )

        create_match_pool(
            [self.make_match(90001, "2040-01-01")],
            created_by=sender_id,
            source_filename="sender-one.xlsx",
        )
        create_match_pool(
            [self.make_match(90002, "2040-01-02")],
            created_by=other_id,
            source_filename="sender-two.xlsx",
        )

        self.client.post("/auth/logout", headers={"X-CSRF-Token": self.csrf_token})
        response = self.login("sender.one", "sender.one")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/matches").status_code, 403)
        self.change_password("sender.one")
        matches = self.client.get("/matches").get_json()["matches"]
        self.assertEqual([match["id"] for match in matches], [90001])
        self.assertEqual(self.client.get("/users").status_code, 403)
        self.assertEqual(self.client.get("/referees").status_code, 200)

    def test_referee_can_edit_only_allowed_own_fields(self):
        referee = load_referees()[0]
        username = str(referee["id"])
        response = self.login(username, username)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/me/matches").status_code, 403)
        self.change_password(username)
        self.assertEqual(self.client.get("/me/matches").status_code, 200)
        self.assertEqual(self.client.get("/referees").status_code, 403)

        forbidden = self.put_json("/me/referee", {"name": "Másik név"})
        self.assertEqual(forbidden.status_code, 400)
        allowed = self.put_json(
            "/me/referee",
            {"residence": "Tesztváros", "has_car": True, "banned_teams": ["Teszt FC"]},
        )
        self.assertEqual(allowed.status_code, 200, allowed.get_json())
        self.assertEqual(allowed.get_json()["referee"]["residence"], "Tesztváros")

        today = datetime.now(ZoneInfo("Europe/Budapest")).date()
        too_late = (today + timedelta(days=4)).isoformat()
        response = self.put_json(
            "/me/referee", {"unavailable_dates": [too_late]}
        )
        self.assertEqual(response.status_code, 400)
        eligible = (today + timedelta(days=5)).isoformat()
        response = self.put_json(
            "/me/referee", {"unavailable_dates": [eligible]}
        )
        self.assertEqual(response.status_code, 200, response.get_json())

    def test_admin_can_create_reset_and_disable_non_referee_accounts(self):
        response = self.login("admin", "admin")
        self.assertEqual(response.status_code, 200)
        self.change_password("admin")
        response = self.post_json(
            "/users", {"username": "new.sender", "role": "sender"}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["initial_password"], "new.sender")

        user = next(
            user for user in self.client.get("/users").get_json()["users"]
            if user["username"] == "new.sender"
        )
        response = self.post_json(
            f"/users/{user['user_id']}/reset-password",
            {"temporary_password": "Temporary123"},
        )
        self.assertEqual(response.status_code, 200)
        account = authenticate("new.sender", "Temporary123")
        self.assertIsNotNone(account)
        self.assertTrue(account["must_change_password"])

        response = self.put_json(
            f"/users/{user['user_id']}/active", {"active": False}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(authenticate("new.sender", "Temporary123"))

    def test_assignment_draft_is_private_until_finalized(self):
        self.login("admin", "admin")
        self.change_password("admin")
        referee = load_referees()[0]
        match = self.make_match(91001, "2040-02-01")
        match["referee"] = {"id": referee["id"], "name": referee["name"]}
        match["assistant"] = []
        upload_id = create_match_pool(
            [self.make_match(91001, "2040-02-01")],
            created_by=None,
            source_filename="workflow.xlsx",
        )

        with patch("services.assigner_service._assign_matches_for_date") as assign_date:
            assign_date.return_value = {
                "success": True,
                "partial": False,
                "capacity_sufficient": True,
                "assignments": [],
                "missing_matches": [],
                "missing_match_ids": [],
                "matches": [match],
                "total_travel_distance": 12.5,
            }
            response = self.post_json(f"/uploads/{upload_id}/assign", {})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["assignment"]["assigned_count"], 1)

        self.client.post("/auth/logout", headers={"X-CSRF-Token": self.csrf_token})
        response = self.login(str(referee["id"]), str(referee["id"]))
        self.assertEqual(response.status_code, 200)
        self.change_password(str(referee["id"]))
        self.assertEqual(self.client.get("/me/matches").get_json()["matches"], [])

        self.client.post("/auth/logout", headers={"X-CSRF-Token": self.csrf_token})
        self.login("admin", "ChangedPass123")
        response = self.post_json(f"/uploads/{upload_id}/finalize", {})
        self.assertEqual(response.status_code, 200, response.get_json())

        self.client.post("/auth/logout", headers={"X-CSRF-Token": self.csrf_token})
        self.login(str(referee["id"]), "ChangedPass123")
        visible = self.client.get("/me/matches").get_json()["matches"]
        self.assertEqual([assigned["id"] for assigned in visible], [91001])


if __name__ == "__main__":
    unittest.main()
