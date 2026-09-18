import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlparse

from app_version import APP_VERSION, PUBLIC_EXE_NAME, PUBLIC_REPOSITORY, PUBLIC_UPDATE_URL


MANIFEST_SCHEMA_VERSION = 1


def _version_tuple(value):
    parts = value.strip().lstrip("v").split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise ValueError("无效版本号")
    return tuple(int(part) for part in parts)


def is_public_build():
    if not getattr(sys, "frozen", False):
        return False
    bundle_root = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.isfile(os.path.join(bundle_root, "public_build.marker"))


def _validate_release(release):
    if not isinstance(release, dict) or release.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("更新信息格式不受支持")
    tag = release.get("tag_name")
    _version_tuple(tag or "")
    if not isinstance(release.get("body"), str) or not release["body"].strip():
        raise ValueError("更新信息缺少中文说明")
    if not isinstance(release.get("published_at"), str) or not release["published_at"].strip():
        raise ValueError("更新信息缺少发布日期")

    expected_prefix = f"/{PUBLIC_REPOSITORY}/releases/download/{tag}/"
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("更新信息缺少下载文件")
    for name in (PUBLIC_EXE_NAME, "SHA256SUMS.txt"):
        asset = _asset(release, name)
        url = asset.get("browser_download_url", "")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or parsed.path != expected_prefix + name:
            raise ValueError(f"{name} 下载地址无效")
    return release


def check_release(url=PUBLIC_UPDATE_URL):
    request = urllib.request.Request(url, headers={"User-Agent": "WTSpeeder-Updater", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    _validate_release(release)
    release["newer"] = _version_tuple(release["tag_name"]) > _version_tuple(APP_VERSION)
    return release


def _asset(release, name):
    for asset in release.get("assets", []):
        if asset.get("name") == name:
            return asset
    raise ValueError(f"Release 缺少 {name}")


def download_release(release):
    if not is_public_build():
        raise RuntimeError("源码或 Private 模式不执行应用替换")
    target_asset = _asset(release, PUBLIC_EXE_NAME)
    checks_asset = _asset(release, "SHA256SUMS.txt")
    directory = tempfile.mkdtemp(prefix="WTSpeeder-update-")
    exe_path = os.path.join(directory, PUBLIC_EXE_NAME)
    sums_path = os.path.join(directory, "SHA256SUMS.txt")
    for asset, path in ((target_asset, exe_path), (checks_asset, sums_path)):
        request = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "WTSpeeder-Updater"})
        with urllib.request.urlopen(request, timeout=60) as response, open(path, "wb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
    expected = None
    with open(sums_path, "r", encoding="utf-8") as handle:
        for line in handle:
            fields = line.strip().split()
            if len(fields) >= 2 and fields[-1].lstrip("*") == PUBLIC_EXE_NAME:
                expected = fields[0].lower()
    digest = hashlib.sha256()
    with open(exe_path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    if not expected or digest.hexdigest() != expected:
        raise ValueError("应用更新文件校验失败")
    return exe_path


def install_on_exit(downloaded_exe):
    current = os.path.abspath(sys.executable)
    directory = os.path.dirname(downloaded_exe)
    script = os.path.join(directory, "install_update.cmd")
    with open(script, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write("@echo off\n")
        handle.write("setlocal\n")
        handle.write(":wait\n")
        handle.write(f'tasklist /FI "PID eq {os.getpid()}" 2>NUL | find "{os.getpid()}" >NUL && (ping 127.0.0.1 -n 2 >NUL & goto wait)\n')
        handle.write(f'copy /Y "{current}" "{current}.old" >NUL || goto failed\n')
        handle.write(f'copy /Y "{downloaded_exe}" "{current}" >NUL || goto failed\n')
        handle.write(f'start "" "{current}"\n')
        handle.write("exit /b 0\n")
        handle.write(":failed\n")
        handle.write(f'start "" explorer.exe /select,"{downloaded_exe}"\n')
    subprocess.Popen(["cmd.exe", "/c", script], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
