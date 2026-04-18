from __future__ import annotations

import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from authorization import AuthorizationService
from csv_manager import CSVManager
from database import DatabaseManager
from repositories import AuditRepository, BackupRepository, MetaRepository, RecordRepository, SourceRepository, UserRepository
from services import AppServices, AuthService, BackupService, LegacyMigrationService, RecordService, UserService
from source_sync import SourceSyncService


class ServiceHarness:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.data_dir = root / "data"
        self.backup_dir = self.data_dir / "backups"
        self.snapshot_dir = self.data_dir / "snapshots"
        self.runtime_backup_dir = self.backup_dir / "runtime"
        self.db_backup_dir = self.backup_dir / "db"
        for directory in [self.data_dir, self.backup_dir, self.snapshot_dir, self.runtime_backup_dir, self.db_backup_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(f"test-harness-{id(self)}")
        self.logger.handlers.clear()
        self.logger.addHandler(logging.NullHandler())
        self.logger.setLevel(logging.INFO)

        self.db_manager = DatabaseManager(self.data_dir / "runtime_store.db", backup_dir=self.db_backup_dir, logger=self.logger)
        self.db_manager.initialize()
        self.csv_manager = CSVManager(
            csv_path=self.data_dir / "records.csv",
            backup_dir=self.backup_dir,
            snapshot_dir=self.snapshot_dir,
            logger=self.logger,
        )
        self.user_repository = UserRepository()
        self.record_repository = RecordRepository()
        self.source_repository = SourceRepository()
        self.audit_repository = AuditRepository()
        self.backup_repository = BackupRepository()
        self.meta_repository = MetaRepository()
        self.authorization_service = AuthorizationService(self.user_repository)
        self.backup_service = BackupService(self.runtime_backup_dir, self.backup_repository, self.logger)
        self.legacy_migration_service = LegacyMigrationService(
            db_manager=self.db_manager,
            csv_manager=self.csv_manager,
            record_repository=self.record_repository,
            meta_repository=self.meta_repository,
            audit_repository=self.audit_repository,
            backup_service=self.backup_service,
            logger=self.logger,
        )
        self.auth_service = AuthService(
            db_manager=self.db_manager,
            user_repository=self.user_repository,
            audit_repository=self.audit_repository,
            meta_repository=self.meta_repository,
            logger=self.logger,
        )
        self.user_service = UserService(
            db_manager=self.db_manager,
            user_repository=self.user_repository,
            audit_repository=self.audit_repository,
            authorization_service=self.authorization_service,
            logger=self.logger,
        )
        self.record_service = RecordService(
            db_manager=self.db_manager,
            record_repository=self.record_repository,
            user_repository=self.user_repository,
            audit_repository=self.audit_repository,
            authorization_service=self.authorization_service,
            backup_service=self.backup_service,
            csv_manager=self.csv_manager,
            logger=self.logger,
        )
        self.source_sync_service = SourceSyncService(
            db_manager=self.db_manager,
            user_repository=self.user_repository,
            source_repository=self.source_repository,
            audit_repository=self.audit_repository,
            csv_manager=self.csv_manager,
            logger=self.logger,
        )
        self.services = AppServices(
            db_manager=self.db_manager,
            auth_service=self.auth_service,
            user_service=self.user_service,
            record_service=self.record_service,
            source_sync_service=self.source_sync_service,
            backup_service=self.backup_service,
            legacy_migration_service=self.legacy_migration_service,
            audit_repository=self.audit_repository,
            source_repository=self.source_repository,
            user_repository=self.user_repository,
            record_repository=self.record_repository,
            meta_repository=self.meta_repository,
        )


class ApplicationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.harness = ServiceHarness(self.root)
        self.super_admin = self.harness.auth_service.bootstrap_super_admin("super.admin", "AdminPassword1", "Super Admin")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_branch(self) -> dict[str, dict[str, object]]:
        region_one = self.harness.user_service.create_user(
            self.super_admin,
            login_id="region.one",
            role="REGIONAL_MANAGER",
            password="RegionPass1A",
            display_name="Region One",
            deployed_location="North",
            phone="1111111111",
            parent_login_id="super.admin",
        )
        region_two = self.harness.user_service.create_user(
            self.super_admin,
            login_id="region.two",
            role="REGIONAL_MANAGER",
            password="RegionPass2A",
            display_name="Region Two",
            deployed_location="South",
            phone="2222222222",
            parent_login_id="super.admin",
        )
        associate = self.harness.user_service.create_user(
            region_one,
            login_id="assoc.one",
            role="ASSOCIATE_MANAGER",
            password="AssocPass1A",
            display_name="Associate One",
            deployed_location="North Hub",
            phone="3333333333",
            parent_login_id="region.one",
        )
        local = self.harness.user_service.create_user(
            associate,
            login_id="local.one",
            role="LOCAL_MANAGER",
            password="LocalPass1A",
            display_name="Local One",
            deployed_location="North City",
            phone="4444444444",
            parent_login_id="assoc.one",
        )
        candidate = self.harness.user_service.create_user(
            local,
            login_id="cand.one",
            role="CANDIDATE",
            password="Candidate1A",
            display_name="Candidate One",
            deployed_location="North City",
            phone="5555555555",
            parent_login_id="local.one",
        )
        candidate_two = self.harness.user_service.create_user(
            self.harness.user_service.get_user_by_login("region.two"),
            login_id="local.two",
            role="LOCAL_MANAGER",
            password="LocalPass2A",
            display_name="Local Two",
            deployed_location="South City",
            phone="6666666666",
            parent_login_id="region.two",
        )
        other_candidate = self.harness.user_service.create_user(
            candidate_two,
            login_id="cand.two",
            role="CANDIDATE",
            password="Candidate2A",
            display_name="Candidate Two",
            deployed_location="South City",
            phone="7777777777",
            parent_login_id="local.two",
        )
        return {
            "region_one": region_one,
            "region_two": region_two,
            "associate": associate,
            "local": local,
            "candidate": candidate,
            "local_two": candidate_two,
            "other_candidate": other_candidate,
        }

    def test_bootstrap_and_login(self) -> None:
        authenticated = self.harness.auth_service.authenticate("super.admin", "AdminPassword1")
        self.assertEqual(authenticated["role"], "SUPER_ADMIN")

    def test_permission_matrix_blocks_cross_branch_updates(self) -> None:
        branch = self._create_branch()
        with self.assertRaises(PermissionError):
            self.harness.user_service.update_user(
                branch["region_one"],
                target_login_id="cand.two",
                display_name="Hacked",
                deployed_location="Elsewhere",
                phone="8888888888",
                parent_login_id="local.two",
                active_flag=True,
            )

    def test_local_manager_can_manage_assigned_candidate_only(self) -> None:
        branch = self._create_branch()
        updated = self.harness.user_service.update_user(
            branch["local"],
            target_login_id="cand.one",
            display_name="Candidate One Updated",
            deployed_location="North City Updated",
            phone="9999999999",
            parent_login_id="local.one",
            active_flag=True,
        )
        self.assertEqual(updated["display_name"], "Candidate One Updated")
        with self.assertRaises(PermissionError):
            self.harness.user_service.update_user(
                branch["local"],
                target_login_id="cand.two",
                display_name="Nope",
                deployed_location="Nope",
                phone="9999999999",
                parent_login_id="local.two",
                active_flag=True,
            )

    def test_candidate_sees_only_own_records_and_referral_equals_login(self) -> None:
        branch = self._create_branch()
        saved = self.harness.record_service.save_record(
            branch["candidate"],
            public_id=None,
            candidate_login_id=None,
            application_number="APP-001",
            name="Customer One",
            phone_number="8888888888",
            status="Open",
            short_note="First",
        )
        self.harness.record_service.save_record(
            branch["other_candidate"],
            public_id=None,
            candidate_login_id=None,
            application_number="APP-002",
            name="Customer Two",
            phone_number="9999999999",
            status="Clone",
            short_note="Second",
        )
        visible = self.harness.record_service.list_records(branch["candidate"])
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["public_id"], saved["public_id"])
        self.assertEqual(visible[0]["candidate_login_id"], "cand.one")

    def test_duplicate_application_number_is_rejected(self) -> None:
        branch = self._create_branch()
        self.harness.record_service.save_record(
            branch["candidate"],
            public_id=None,
            candidate_login_id=None,
            application_number="APP-UNIQUE",
            name="Customer One",
            phone_number="8888888888",
            status="Open",
            short_note="First",
        )
        with self.assertRaises(ValueError):
            self.harness.record_service.save_record(
                branch["candidate"],
                public_id=None,
                candidate_login_id=None,
                application_number="APP-UNIQUE",
                name="Customer Two",
                phone_number="7777777777",
                status="Clone",
                short_note="Second",
            )

    def test_record_save_creates_version_and_backup(self) -> None:
        branch = self._create_branch()
        saved = self.harness.record_service.save_record(
            branch["candidate"],
            public_id=None,
            candidate_login_id=None,
            application_number="APP-300",
            name="Customer One",
            phone_number="8888888888",
            status="In Progress",
            short_note="Initial",
        )
        updated = self.harness.record_service.save_record(
            branch["candidate"],
            public_id=str(saved["public_id"]),
            candidate_login_id=None,
            application_number="APP-300",
            name="Customer One Updated",
            phone_number="8888888888",
            status="Forfeited",
            short_note="Updated",
        )
        versions = self.harness.record_service.list_versions(branch["candidate"], str(saved["public_id"]))
        self.assertEqual(len(versions), 2)
        self.assertEqual(updated["version_number"], 2)
        with self.harness.db_manager.connection() as connection:
            backups = self.harness.backup_repository.list_backups(connection, limit=20)
        self.assertTrue(any(backup["target_id"] == saved["public_id"] for backup in backups))

    def test_record_restore_recovers_previous_snapshot(self) -> None:
        branch = self._create_branch()
        saved = self.harness.record_service.save_record(
            branch["candidate"],
            public_id=None,
            candidate_login_id=None,
            application_number="APP-400",
            name="Original Name",
            phone_number="8888888888",
            status="Open",
            short_note="v1",
        )
        self.harness.record_service.save_record(
            branch["candidate"],
            public_id=str(saved["public_id"]),
            candidate_login_id=None,
            application_number="APP-400",
            name="Mutated Name",
            phone_number="9999999999",
            status="Clone",
            short_note="v2",
        )
        versions = self.harness.record_service.list_versions(branch["candidate"], str(saved["public_id"]))
        version_to_restore = next(version for version in versions if version["version_number"] == 1)
        restored = self.harness.record_service.restore_version(branch["local"], int(version_to_restore["version_id"]))
        self.assertEqual(restored["name"], "Original Name")
        self.assertEqual(restored["status"], "Open")

    def test_hierarchy_tree_is_scoped_to_authorized_subtree(self) -> None:
        branch = self._create_branch()
        tree = self.harness.user_service.build_tree(branch["region_one"])

        def flatten(nodes: list[dict[str, object]]) -> list[str]:
            result: list[str] = []
            for node in nodes:
                result.append(str(node["login_id"]))
                result.extend(flatten(node["children"]))
            return result

        flattened = flatten(tree)
        self.assertIn("region.one", flattened)
        self.assertIn("cand.one", flattened)
        self.assertNotIn("region.two", flattened)
        self.assertNotIn("cand.two", flattened)

    def test_source_preview_and_commit_offline_path(self) -> None:
        csv_path = self.root / "source.csv"
        csv_path.write_text(
            "login_id,role,display_name,parent_login_id,password,deployed_location,phone\n"
            "region.csv,REGIONAL_MANAGER,Region CSV,super.admin,RegionCsvPass1,Remote North,1212121212\n"
            "local.csv,LOCAL_MANAGER,Local CSV,region.csv,LocalCsvPass1,Remote North City,1313131313\n"
            "cand.csv,CANDIDATE,Candidate CSV,local.csv,CandidateCsv1,Remote North City,1414141414\n",
            encoding="utf-8",
        )
        preview = self.harness.source_sync_service.preview_source(
            self.super_admin,
            source_mode="OFFLINE",
            local_path=str(csv_path),
            remote_url="",
        )
        self.assertEqual(preview["accepted_row_count"], 3)
        result = self.harness.source_sync_service.commit_preview(self.super_admin, preview)
        self.assertEqual(result["accepted_row_count"], 3)
        imported_candidate = self.harness.user_service.get_user_by_login("cand.csv")
        self.assertIsNotNone(imported_candidate)
        self.assertEqual(imported_candidate["role"], "CANDIDATE")

    def test_invalid_offline_path_and_online_source_fail_safely(self) -> None:
        with self.assertRaises(ValueError):
            self.harness.source_sync_service.preview_source(
                self.super_admin,
                source_mode="OFFLINE",
                local_path=str(self.root / "missing.csv"),
                remote_url="",
            )

        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self.payload = payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return self.payload

        payload = b"login_id,role,display_name,parent_login_id,password\nregion.web,REGIONAL_MANAGER,Region Web,super.admin,RegionWebPass1\n"
        with patch("source_sync.urlopen", return_value=FakeResponse(payload)):
            preview = self.harness.source_sync_service.preview_source(
                self.super_admin,
                source_mode="ONLINE",
                local_path="",
                remote_url="https://example.com/users.csv",
            )
        self.assertEqual(preview["accepted_row_count"], 1)

    def test_duplicate_rows_and_malformed_source_are_reported(self) -> None:
        duplicate_csv = self.root / "duplicate.csv"
        duplicate_csv.write_text(
            "login_id,role,display_name,parent_login_id,password\n"
            "region.dup,REGIONAL_MANAGER,Region Dup,super.admin,RegionDupPass1\n"
            "region.dup,REGIONAL_MANAGER,Region Dup Again,super.admin,RegionDupPass2\n",
            encoding="utf-8",
        )
        preview = self.harness.source_sync_service.preview_source(
            self.super_admin,
            source_mode="OFFLINE",
            local_path=str(duplicate_csv),
            remote_url="",
        )
        self.assertEqual(preview["accepted_row_count"], 1)
        self.assertEqual(preview["rejected_row_count"], 1)

        malformed_csv = self.root / "malformed.csv"
        malformed_csv.write_text("login_id,display_name\nbroken,Missing Role\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.harness.source_sync_service.preview_source(
                self.super_admin,
                source_mode="OFFLINE",
                local_path=str(malformed_csv),
                remote_url="",
            )

    def test_legacy_csv_migration_preserves_records(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        migration_root = Path(temp_dir.name)
        harness = ServiceHarness(migration_root)
        legacy_csv = harness.data_dir / "records.csv"
        legacy_csv.write_text(
            "record_id,title,category,name,phone_number,status,short_note,created_at,updated_at\n"
            "REC-LEGACY-1,Legacy Title,Legacy Cat,Legacy Name,9090909090,Close,legacy note,2026-01-01 10:00:00,2026-01-02 11:00:00\n",
            encoding="utf-8-sig",
        )
        migrated_count = harness.legacy_migration_service.migrate_if_needed()
        self.assertEqual(migrated_count, 1)
        records = harness.record_service.list_records({"user_id": 1, "role": "SUPER_ADMIN", "login_id": "ghost"})
        self.assertEqual(records[0]["public_id"], "REC-LEGACY-1")
        self.assertEqual(records[0]["application_number"], "REC-LEGACY-1")
        self.assertEqual(records[0]["status"], "Forfeited")
        temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
