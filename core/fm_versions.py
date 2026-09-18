import csv
import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from datetime import datetime, timezone

from config import APP_NAME, resource_path


SCHEMA_VERSION = 1
INDEX_URL = "https://raw.githubusercontent.com/KaerMorh/WTSpeeder/main/FM/index.json"
CSV_FILES = ("fm_data_db.csv", "fm_names_db.csv")


def _user_root():
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME, "fm")


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def _write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def _published_key(version):
    return (version.get("published_at", ""), version.get("id", ""))


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_csv_pair(directory):
    expected = {
        "fm_data_db.csv": ["Name", "Length", "WingSpan", "WingArea", "EmptyMass", "MaxFuelMass", "CritAirSpd", "CritAirSpdMach"],
        "fm_names_db.csv": ["Name", "FmName", "Type", "English"],
    }
    for filename, prefix in expected.items():
        path = os.path.join(directory, filename)
        with open(path, "r", encoding="utf-8", newline="") as handle:
            rows = csv.reader(handle, delimiter=";")
            header = next(rows, [])
            if header[:len(prefix)] != prefix:
                raise ValueError(f"{filename} 表头无效")
            seen = set()
            count = 0
            for row in rows:
                if not row or not row[0].strip():
                    continue
                if row[0] in seen:
                    raise ValueError(f"{filename} 包含重复键: {row[0]}")
                seen.add(row[0])
                count += 1
            if not count:
                raise ValueError(f"{filename} 没有有效数据")


class FMVersionManager:
    def __init__(self, root=None, builtin_root=None, index_url=INDEX_URL):
        self.root = root or _user_root()
        self.versions_root = os.path.join(self.root, "versions")
        self.state_path = os.path.join(self.root, "state.json")
        self.builtin_root = builtin_root or resource_path("FM")
        self.builtin_index_path = os.path.join(self.builtin_root, "index.json")
        self.index_url = index_url
        self.state = _read_json(self.state_path, {})
        self.index = self.state.get("index") or _read_json(self.builtin_index_path, {"versions": []})
        self.current_id = None

    @property
    def compatible_versions(self):
        return sorted(
            [v for v in self.index.get("versions", []) if v.get("schema_version") == SCHEMA_VERSION],
            key=_published_key,
            reverse=True,
        )

    def version(self, version_id):
        for version in self.index.get("versions", []):
            if version.get("id") == version_id:
                return version
        return None

    def latest(self):
        versions = self.compatible_versions
        return versions[0] if versions else None

    def latest_published(self):
        versions = sorted(self.index.get("versions", []), key=_published_key, reverse=True)
        return versions[0] if versions else None

    def _builtin_directory(self, version_id):
        path = os.path.join(self.builtin_root, "versions", version_id)
        return path if os.path.isdir(path) else None

    def _cached_directory(self, version_id):
        path = os.path.join(self.versions_root, version_id)
        return path if os.path.isdir(path) else None

    def directory(self, version_id):
        return self._cached_directory(version_id) or self._builtin_directory(version_id)

    def resolve_for_startup(self):
        stable_id = self.index.get("stable_id")
        requested = self.state.get("selected_id") or stable_id
        directory = self.directory(requested)
        if not directory:
            requested = stable_id
            directory = self.directory(requested)
        if not directory:
            directory = self.builtin_root
            requested = stable_id or "builtin"
        try:
            validate_csv_pair(directory)
        except (OSError, ValueError):
            directory = self.builtin_root
            requested = stable_id or "builtin"
        self.current_id = requested
        self.state["running_id"] = requested
        _write_json(self.state_path, self.state)
        return directory

    def choose(self, version_id):
        version = self.version(version_id)
        if not version:
            raise ValueError("未知 FM 版本")
        if version.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("此 FM 版本需要升级应用")
        if not self.directory(version_id):
            self._download_version(version)
        self.state["selected_id"] = version_id
        self.state["selection_is_manual"] = True
        _write_json(self.state_path, self.state)
        self.cleanup()

    def _download(self, url, destination):
        request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}-FM-Updater"})
        with urllib.request.urlopen(request, timeout=30) as response, open(destination, "wb") as output:
            shutil.copyfileobj(response, output)

    def _download_version(self, version):
        os.makedirs(self.versions_root, exist_ok=True)
        temporary = tempfile.mkdtemp(prefix=".download-", dir=self.versions_root)
        try:
            for filename in CSV_FILES:
                metadata = version["files"][filename]
                path = os.path.join(temporary, filename)
                self._download(metadata["url"], path)
                if os.path.getsize(path) != metadata["size"] or _sha256(path) != metadata["sha256"]:
                    raise ValueError(f"{filename} 校验失败")
            validate_csv_pair(temporary)
            with open(os.path.join(temporary, "manifest.json"), "w", encoding="utf-8") as handle:
                json.dump(version, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            target = os.path.join(self.versions_root, version["id"])
            if os.path.exists(target):
                shutil.rmtree(temporary)
            else:
                os.replace(temporary, target)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def sync(self):
        os.makedirs(self.root, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="index-", suffix=".json", dir=self.root)
        os.close(fd)
        try:
            self._download(self.index_url, temporary)
            remote = _read_json(temporary, None)
            if not isinstance(remote, dict) or not isinstance(remote.get("versions"), list):
                raise ValueError("远端 FM 索引无效")
            compatible = sorted(
                [v for v in remote["versions"] if v.get("schema_version") == SCHEMA_VERSION],
                key=_published_key,
                reverse=True,
            )
            wanted = {v["id"] for v in compatible[:2]}
            if remote.get("stable_id"):
                wanted.add(remote["stable_id"])
            if self.state.get("selected_id"):
                wanted.add(self.state["selected_id"])
            if self.current_id or self.state.get("running_id"):
                wanted.add(self.current_id or self.state.get("running_id"))
            by_id = {v.get("id"): v for v in remote["versions"]}
            for version_id in wanted:
                version = by_id.get(version_id)
                if version and version.get("schema_version") == SCHEMA_VERSION and not self.directory(version_id):
                    self._download_version(version)
            if not self.state.get("selection_is_manual") and compatible:
                self.state["selected_id"] = compatible[0]["id"]
            self.index = remote
            self.state["index"] = remote
            self.state["last_checked_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            _write_json(self.state_path, self.state)
            self.cleanup()
            return compatible
        finally:
            try:
                os.remove(temporary)
            except OSError:
                pass

    def cleanup(self):
        if not os.path.isdir(self.versions_root):
            return
        keep = {v["id"] for v in self.compatible_versions[:2]}
        for value in (self.index.get("stable_id"), self.state.get("selected_id"), self.current_id, self.state.get("running_id")):
            if value:
                keep.add(value)
        for name in os.listdir(self.versions_root):
            path = os.path.join(self.versions_root, name)
            if name.startswith(".download-") or not os.path.isdir(path):
                continue
            if name in keep or not self.version(name):
                continue
            shutil.rmtree(path)
