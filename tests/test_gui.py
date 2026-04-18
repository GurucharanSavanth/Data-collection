from __future__ import annotations

import logging
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from gui import RecordManagerApp
from session_manager import SessionManager
from test_application import ServiceHarness


class GuiSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.harness = ServiceHarness(self.root_path)
        self.super_admin = self.harness.auth_service.bootstrap_super_admin("super.admin", "AdminPassword1", "Super Admin")
        self.root = tk.Tk()
        self.root.withdraw()
        self.session_manager = SessionManager(
            session_path=self.root_path / "session" / "session_state.json",
            app_state_path=self.root_path / "session" / "app_state.json",
            logger=logging.getLogger(f"gui-test-{id(self)}"),
        )
        (self.root_path / "session").mkdir(parents=True, exist_ok=True)
        self.app = RecordManagerApp(
            root=self.root,
            settings={"window_title": "Test App", "default_window_size": "1200x800"},
            services=self.harness.services,
            session_manager=self.session_manager,
            logger=logging.getLogger(f"gui-test-app-{id(self)}"),
            data_dir=self.harness.data_dir,
        )

    def tearDown(self) -> None:
        self.app.root.destroy()
        self.temp_dir.cleanup()

    def test_bootstrap_or_login_view_exists(self) -> None:
        self.assertIn(self.app.current_view, {"bootstrap", "login"})

    def test_candidate_dashboard_has_required_columns_and_button_text(self) -> None:
        regional = self.harness.user_service.create_user(
            self.super_admin,
            login_id="region.one",
            role="REGIONAL_MANAGER",
            password="RegionPassword1",
            display_name="Region One",
            deployed_location="North",
            phone="1111111111",
            parent_login_id="super.admin",
        )
        local = self.harness.user_service.create_user(
            regional,
            login_id="local.one",
            role="LOCAL_MANAGER",
            password="LocalPassword1",
            display_name="Local One",
            deployed_location="North City",
            phone="1111111111",
            parent_login_id="region.one",
        )
        candidate = self.harness.user_service.create_user(
            local,
            login_id="cand.one",
            role="CANDIDATE",
            password="Candidate1A",
            display_name="Candidate One",
            deployed_location="North City",
            phone="2222222222",
            parent_login_id="local.one",
        )
        self.app.current_user = candidate
        self.app.build_dashboard_view()
        self.root.update_idletasks()
        self.assertEqual(self.app.new_record_button["text"], "New Record Report")
        self.assertEqual(
            self.app.record_tree["columns"],
            ("public_id", "name", "phone_number", "created_at", "candidate_login_id"),
        )

    def test_super_admin_dashboard_has_source_and_audit_tabs(self) -> None:
        self.app.current_user = self.super_admin
        self.app.build_dashboard_view()
        self.root.update_idletasks()
        tab_texts = [self.app.notebook.tab(tab_id, "text") for tab_id in self.app.notebook.tabs()]
        self.assertIn("Credential Source", tab_texts)
        self.assertIn("Audit / Recovery", tab_texts)


if __name__ == "__main__":
    unittest.main()
