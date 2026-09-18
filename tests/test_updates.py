import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from core.app_update import _version_tuple
from core.fm_versions import FMVersionManager, validate_csv_pair
from FM.update_fm import (
    BlkxParser, FM_DATA_COLUMNS, FM_NAMES_COLUMNS, _write_records, run_automation,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class LocalFMVersionManager(FMVersionManager):
    def _download(self, url, destination):
        shutil.copyfile(url, destination)


class FMVersionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_frozen_baseline_matches_original(self):
        version_id = "fm-20260918-054634-manual"
        manifest = json.loads((REPO_ROOT / "FM" / "versions" / version_id / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["notes"], "问鼎九天版本FM")
        for filename in ("fm_data_db.csv", "fm_names_db.csv"):
            original = (REPO_ROOT / "FM" / filename).read_bytes()
            frozen = (REPO_ROOT / "FM" / "versions" / version_id / filename).read_bytes()
            self.assertEqual(original, frozen)
            self.assertEqual(hashlib.sha256(frozen).hexdigest(), manifest["files"][filename]["sha256"])

    def test_latest_is_by_publication_time_not_kind(self):
        manager = FMVersionManager(root=str(self.root / "cache"), builtin_root=str(REPO_ROOT / "FM"))
        manager.index = {
            "stable_id": "new-manual",
            "versions": [
                {"id": "old-auto", "published_at": "2026-01-01T00:00:00Z", "kind": "automatic", "schema_version": 1},
                {"id": "new-manual", "published_at": "2026-02-01T00:00:00Z", "kind": "manual", "schema_version": 1},
            ],
        }
        self.assertEqual(manager.latest()["id"], "new-manual")

    def test_download_hash_failure_keeps_existing_selection(self):
        source = self.root / "source"
        source.mkdir()
        for filename in ("fm_data_db.csv", "fm_names_db.csv"):
            shutil.copyfile(REPO_ROOT / "FM" / filename, source / filename)
        version = {
            "id": "bad",
            "published_at": "2026-02-01T00:00:00Z",
            "kind": "automatic",
            "schema_version": 1,
            "files": {
                name: {"url": str(source / name), "size": (source / name).stat().st_size, "sha256": "0" * 64}
                for name in ("fm_data_db.csv", "fm_names_db.csv")
            },
        }
        manager = LocalFMVersionManager(root=str(self.root / "cache"), builtin_root=str(REPO_ROOT / "FM"))
        manager.index = {"stable_id": "fm-20260918-054634-manual", "versions": [version]}
        manager.state["selected_id"] = "fm-20260918-054634-manual"
        with self.assertRaises(ValueError):
            manager._download_version(version)
        self.assertEqual(manager.state["selected_id"], "fm-20260918-054634-manual")
        self.assertFalse((self.root / "cache" / "versions" / "bad").exists())

    def test_version_comparison(self):
        self.assertGreater(_version_tuple("v0.3.0"), _version_tuple("0.2.9"))
        self.assertEqual(_version_tuple("0.3.0"), (0, 3, 0))

    def test_cleanup_keeps_latest_two_stable_selected_and_running(self):
        manager = FMVersionManager(root=str(self.root / "cache"), builtin_root=str(REPO_ROOT / "FM"))
        manager.index = {
            "stable_id": "v1",
            "versions": [
                {"id": f"v{i}", "published_at": f"2026-01-0{i}T00:00:00Z", "schema_version": 1}
                for i in range(1, 6)
            ],
        }
        manager.state.update({"selected_id": "v2", "running_id": "v3"})
        for version_id in ("v1", "v2", "v3", "v4", "v5"):
            (Path(manager.versions_root) / version_id).mkdir(parents=True)
        manager.cleanup()
        remaining = {path.name for path in Path(manager.versions_root).iterdir()}
        self.assertEqual(remaining, {"v1", "v2", "v3", "v4", "v5"})
        manager.state.update({"selected_id": "v5", "running_id": "v5"})
        manager.cleanup()
        remaining = {path.name for path in Path(manager.versions_root).iterdir()}
        self.assertEqual(remaining, {"v1", "v4", "v5"})

    def test_csv_validation(self):
        validate_csv_pair(str(REPO_ROOT / "FM"))

    def test_automation_initializes_once_and_publishes_real_change(self):
        repo = self.root / "repo"
        fm_root = repo / "FM"
        source = self.root / "flightmodels"
        (fm_root / "versions" / "manual").mkdir(parents=True)
        (source / "fm").mkdir(parents=True)
        fm_json = {
            "Length": 10,
            "Aerodynamics": {"WingPlane": {"Span": 9, "Strength": {"VNE": 700, "MNE": 0.9}}},
            "Mass": {"EmptyMass": 1000, "MaxFuelMass0": 200, "GearDestructionIndSpeed": 400},
        }
        unit_json = {"fmFile": "fm/plane.blk", "type": "typeFighter"}
        (source / "fm" / "plane.blkx").write_text(json.dumps(fm_json), encoding="utf-8")
        (source / "unit.blkx").write_text(json.dumps(unit_json), encoding="utf-8")
        record = BlkxParser.extract_fm_data(json.dumps(fm_json), "plane")
        _write_records(fm_root / "fm_data_db.csv", {"plane": record}, FM_DATA_COLUMNS)
        names = {"unit": {"Name": "unit", "FmName": "plane", "Type": "fighter", "English": ""}}
        _write_records(fm_root / "fm_names_db.csv", names, FM_NAMES_COLUMNS)
        (fm_root / "index.json").write_text(json.dumps({
            "schema_version": 1,
            "stable_id": "manual",
            "versions": [{"id": "manual", "published_at": "2026-01-01T00:00:00Z", "kind": "manual", "schema_version": 1}],
        }), encoding="utf-8")
        (fm_root / "check_state.json").write_text('{"last_checked_commit": ""}', encoding="utf-8")

        run_automation(str(source), "1" * 40, str(repo))
        index = json.loads((fm_root / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["stable_id"], "manual")
        self.assertEqual(sum(v["kind"] == "automatic" for v in index["versions"]), 1)
        self.assertEqual(index["versions"][0]["notes"], "首次自动构建，与人工稳定版数据一致")
        run_automation(str(source), "1" * 40, str(repo))
        run_automation(str(source), "2" * 40, str(repo))
        index = json.loads((fm_root / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(v["kind"] == "automatic" for v in index["versions"]), 1)

        fm_json["Length"] = 11
        (source / "fm" / "plane.blkx").write_text(json.dumps(fm_json), encoding="utf-8")
        run_automation(str(source), "3" * 40, str(repo))
        index = json.loads((fm_root / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(v["kind"] == "automatic" for v in index["versions"]), 2)
        self.assertIn("更新 1 个机型", index["versions"][0]["notes"])
        self.assertEqual(index["stable_id"], "manual")


if __name__ == "__main__":
    unittest.main()
