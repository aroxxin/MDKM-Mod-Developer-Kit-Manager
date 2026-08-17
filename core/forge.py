from __future__ import annotations

import hashlib
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from zipfile import BadZipFile, ZipFile

from core.app import cache_get, cache_set, load_config
from core.retry import with_retry

FORGE_BASE = "https://files.minecraftforge.net/net/minecraftforge/forge"
FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"
USER_AGENT = "MDK-Manager/0.2"


class ForgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ForgeRelease:
    minecraft: str
    forge: str
    mdk_url: str
    sha1: str | None = None
    md5: str | None = None


def _version_key(value: str) -> tuple:
    result = []
    for part in re.split(r"[._-]", value):
        result.append((0, int(part)) if part.isdigit() else (1, part.lower()))
    return tuple(result)


def _open_url(url: str, timeout: int = 30):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise ForgeError(f"Serwer zwrócił HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise ForgeError(f"Nie można połączyć się z Forge: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ForgeError("Przekroczono czas połączenia z Forge.") from exc


def fetch_text(url: str) -> str:
    with _open_url(url) as response:
        return response.read().decode("utf-8", errors="replace")


def get_supported_minecraft_versions() -> list[str]:
    config = load_config()
    if config.get("cache_enabled", True):
        cached = cache_get("forge_minecraft_versions", int(config.get("cache_ttl_hours", 12)))
        if isinstance(cached, list) and cached:
            return cached
    html = with_retry(lambda: fetch_text(FORGE_BASE + "/"), attempts=int(config.get("download_retries", 3)))
    versions: set[str] = set()

    for match in re.finditer(r'href=["\']index_([^"\']+)\.html["\']', html, re.I):
        version = match.group(1)
        if re.fullmatch(r"\d+(?:\.\d+){1,2}", version):
            versions.add(version)

    if not versions:
        raise ForgeError("Nie udało się odczytać listy wersji Minecraft z Forge.")

    result = sorted(versions, key=_version_key, reverse=True)
    if config.get("cache_enabled", True):
        cache_set("forge_minecraft_versions", result)
    return result


def _canonical_mdk_url(minecraft: str, forge: str) -> str:
    return f"{FORGE_MAVEN}/{minecraft}-{forge}/forge-{minecraft}-{forge}-mdk.zip"


def _parse_release_page(minecraft_version: str, html: str) -> list[ForgeRelease]:
    releases: list[ForgeRelease] = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.I | re.S)

    for row in rows:
        version_match = re.search(r"<td[^>]*>\s*([0-9]+(?:\.[0-9]+){1,3})\s*</td>", row, re.I)
        if not version_match:
            continue
        forge_version = version_match.group(1).strip()
        if not re.search(r"\bMdk\b", row, re.I):
            continue

        mdk_url = _canonical_mdk_url(minecraft_version, forge_version)
        mdk_section_match = re.search(r"\bMdk\b(.*)", row, re.I | re.S)
        mdk_section = mdk_section_match.group(1) if mdk_section_match else ""
        sha1_match = re.search(r"SHA1:\s*([a-f0-9]{40})", mdk_section, re.I)
        md5_match = re.search(r"MD5:\s*([a-f0-9]{32})", mdk_section, re.I)
        releases.append(ForgeRelease(
            minecraft=minecraft_version,
            forge=forge_version,
            mdk_url=mdk_url,
            sha1=sha1_match.group(1).lower() if sha1_match else None,
            md5=md5_match.group(1).lower() if md5_match else None,
        ))

    if not releases:
        pattern = re.compile(r"([0-9]+(?:\.[0-9]+){1,3}).{0,5000}?\bMdk\b.{0,2000}?SHA1:\s*([a-f0-9]{40})", re.I | re.S)
        for match in pattern.finditer(html):
            forge_version, sha1 = match.groups()
            releases.append(ForgeRelease(
                minecraft=minecraft_version,
                forge=forge_version,
                mdk_url=_canonical_mdk_url(minecraft_version, forge_version),
                sha1=sha1.lower(),
            ))

    unique = {release.forge: release for release in releases}
    return sorted(unique.values(), key=lambda r: _version_key(r.forge), reverse=True)


def get_releases(minecraft_version: str) -> list[ForgeRelease]:
    if minecraft_version == "latest":
        minecraft_version = get_supported_minecraft_versions()[0]
    url = f"{FORGE_BASE}/index_{minecraft_version}.html"
    config = load_config()
    cache_key = f"forge_releases_{minecraft_version}"
    if config.get("cache_enabled", True):
        cached = cache_get(cache_key, int(config.get("cache_ttl_hours", 12)))
        if isinstance(cached, list):
            return [ForgeRelease(**item) for item in cached]
    html = with_retry(lambda: fetch_text(url), attempts=int(config.get("download_retries", 3)))
    releases = _parse_release_page(minecraft_version, html)
    if not releases:
        raise ForgeError(f"Brak dostępnego MDK Forge dla Minecraft {minecraft_version}.")
    if config.get("cache_enabled", True):
        cache_set(cache_key, [r.__dict__ for r in releases])
    return releases


def get_latest_release(minecraft_version: str) -> ForgeRelease:
    return get_releases(minecraft_version)[0]


def sha1_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def md5_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.md5()
    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, destination: Path, progress_callback: Callable[[int, int, float], None] | None = None, chunk_size: int = 256 * 1024) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    started = time.monotonic()
    downloaded = 0
    try:
        with _open_url(url, timeout=60) as response:
            raw_total = response.headers.get("Content-Length")
            total = int(raw_total) if raw_total and raw_total.isdigit() else 0
            with temporary.open("wb") as file:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    file.write(chunk)
                    downloaded += len(chunk)
                    elapsed = max(time.monotonic() - started, 0.001)
                    speed = downloaded / elapsed
                    if progress_callback:
                        progress_callback(downloaded, total, speed)
        if downloaded == 0:
            raise ForgeError("Serwer nie zwrócił żadnych danych dla MDK.")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def verify_release(path: Path, release: ForgeRelease) -> tuple[bool, str]:
    if not path.exists():
        return False, "Plik MDK nie istnieje."
    if path.stat().st_size == 0:
        return False, "Pobrany plik MDK ma 0 bajtów."
    if release.sha1:
        actual = sha1_file(path)
        if actual.lower() != release.sha1.lower():
            return False, f"SHA1 nie pasuje: {actual} != {release.sha1}"
        return True, "SHA1 OK"
    if release.md5:
        actual = md5_file(path)
        if actual.lower() != release.md5.lower():
            return False, f"MD5 nie pasuje: {actual} != {release.md5}"
        return True, "MD5 OK"
    return True, "Brak sumy kontrolnej na stronie Forge."


def extract_mdk(archive: Path, target: Path) -> None:
    if not archive.exists() or archive.stat().st_size == 0:
        raise ForgeError("Nie można rozpakować pustego pliku MDK.")
    try:
        with ZipFile(archive, "r") as zip_file:
            bad_member = zip_file.testzip()
            if bad_member is not None:
                raise ForgeError(f"Archiwum MDK jest uszkodzone: {bad_member}")
            zip_file.extractall(target)
    except BadZipFile as exc:
        raise ForgeError("Pobrany plik nie jest poprawnym archiwum ZIP.") from exc
