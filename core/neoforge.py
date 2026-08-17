from __future__ import annotations

import io
import json
import re
import shutil
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from core.app import cache_get, cache_set, load_config
from core.retry import with_retry

GITHUB_API = "https://api.github.com"
NEOFORGE_MDK_ORG = "NeoForgeMDKs"
USER_AGENT = "MDK-Manager/4.0"


class NeoForgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class NeoForgeTemplate:
    minecraft: str
    neoforge: str
    loader_range: str
    repository: str
    archive_url: str


def _version_key(value: str) -> tuple:
    result = []
    for part in re.split(r"[._-]", value):
        result.append((0, int(part)) if part.isdigit() else (1, part.lower()))
    return tuple(result)


def _open_url(url: str, timeout: int = 30):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json, application/json"})
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise NeoForgeError(f"Serwer NeoForge/GitHub zwrócił HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise NeoForgeError(f"Nie można połączyć się z NeoForge/GitHub: {exc.reason}") from exc
    except TimeoutError as exc:
        raise NeoForgeError("Przekroczono czas połączenia z NeoForge/GitHub.") from exc


def fetch_json(url: str):
    with _open_url(url) as response:
        try:
            return json.loads(response.read().decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise NeoForgeError("NeoForge/GitHub zwrócił niepoprawną odpowiedź JSON.") from exc


def _parse_properties(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _repo_name(minecraft: str) -> str:
    return f"MDK-{minecraft}-NeoGradle"


def get_supported_minecraft_versions() -> list[str]:
    config = load_config()
    if config.get("cache_enabled", True):
        cached = cache_get("neoforge_minecraft_versions", int(config.get("cache_ttl_hours", 12)))
        if isinstance(cached, list) and cached:
            return cached
    repos: list[dict] = []
    page = 1
    while page <= 5:
        url = f"{GITHUB_API}/orgs/{NEOFORGE_MDK_ORG}/repos?per_page=100&page={page}&type=public"
        batch = with_retry(lambda url=url: fetch_json(url), attempts=int(config.get("download_retries", 3)))
        if not isinstance(batch, list):
            raise NeoForgeError("GitHub zwrócił niepoprawną listę repozytoriów NeoForge MDK.")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    versions = set()
    prefix = "MDK-"
    suffix = "-NeoGradle"
    for repo in repos:
        name = repo.get("name", "")
        if name.startswith(prefix) and name.endswith(suffix):
            version = name[len(prefix):-len(suffix)]
            if version:
                versions.add(version)
    if not versions:
        raise NeoForgeError("Nie znaleziono oficjalnych wersji NeoForge MDK.")
    result = sorted(versions, key=_version_key, reverse=True)
    if config.get("cache_enabled", True):
        cache_set("neoforge_minecraft_versions", result)
    return result


def _template_archive(repo: str) -> bytes:
    url = f"https://github.com/{NEOFORGE_MDK_ORG}/{repo}/archive/refs/heads/main.zip"
    with _open_url(url, timeout=60) as response:
        return response.read()


def get_template(minecraft_version: str) -> NeoForgeTemplate:
    if minecraft_version == "latest":
        minecraft_version = get_supported_minecraft_versions()[0]
    repo = _repo_name(minecraft_version)
    archive = _template_archive(repo)
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        properties_name = next((name for name in zf.namelist() if name.endswith("/gradle.properties")), None)
        if not properties_name:
            raise NeoForgeError("Template NeoForge nie zawiera gradle.properties.")
        properties = _parse_properties(zf.read(properties_name).decode("utf-8", errors="replace"))
    template_minecraft = properties.get("minecraft_version")
    neoforge = properties.get("neo_version")
    loader_range = properties.get("loader_version_range", "[1,)")
    if not template_minecraft or not neoforge:
        raise NeoForgeError("Nie udało się odczytać wersji Minecraft/NeoForge z template NeoForge.")
    if template_minecraft != minecraft_version:
        raise NeoForgeError(f"Template NeoForge '{repo}' jest dla Minecraft {template_minecraft}, a wybrano {minecraft_version}.")
    return NeoForgeTemplate(template_minecraft, neoforge, loader_range, repo,
                            f"https://github.com/{NEOFORGE_MDK_ORG}/{repo}/archive/refs/heads/main.zip")


def _safe_member_path(root: Path, member: str) -> Path:
    target = (root / member).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise NeoForgeError(f"Niebezpieczna ścieżka w template: {member}")
    return target


def create_project(template: NeoForgeTemplate, target: Path, mod_name: str, mod_id: str | None = None) -> None:
    target = target.expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise NeoForgeError(f"Katalog już istnieje i nie jest pusty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    mod_id = mod_id or re.sub(r"[^a-z0-9_]+", "_", mod_name.lower()).strip("_")
    if not mod_id:
        raise NeoForgeError("Nie udało się utworzyć poprawnego Mod ID z nazwy moda.")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", mod_id):
        raise NeoForgeError("Wygenerowany Mod ID NeoForge nie spełnia wymagań [a-z][a-z0-9_]{1,63}.")
    archive = _template_archive(template.repository)
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        roots = {m.filename.split("/", 1)[0] for m in members if "/" in m.filename}
        if len(roots) != 1:
            raise NeoForgeError("Nie udało się ustalić katalogu głównego template NeoForge.")
        prefix = next(iter(roots)) + "/"
        for member in members:
            if not member.filename.startswith(prefix):
                continue
            relative = member.filename[len(prefix):]
            if not relative:
                continue
            destination = _safe_member_path(target, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as source, destination.open("wb") as dest:
                shutil.copyfileobj(source, dest)
    _replace_project_metadata(target, mod_name, mod_id, template)


def _replace_project_metadata(target: Path, mod_name: str, mod_id: str, template: NeoForgeTemplate) -> None:
    properties_path = target / "gradle.properties"
    if properties_path.exists():
        text = properties_path.read_text(encoding="utf-8")
        replacements = {"minecraft_version": template.minecraft, "neo_version": template.neoforge,
                        "loader_version_range": template.loader_range, "mod_id": mod_id, "mod_name": mod_name}
        for key, value in replacements.items():
            text = re.sub(rf"(?m)^{re.escape(key)}=.*$", f"{key}={value}", text)
        properties_path.write_text(text, encoding="utf-8")
    settings = target / "settings.gradle"
    if settings.exists():
        text = settings.read_text(encoding="utf-8")
        if re.search(r"(?m)^rootProject\.name", text):
            text = re.sub(r"(?m)^rootProject\.name\s*=\s*['\"][^'\"]+['\"]", f"rootProject.name = '{mod_id}'", text)
        settings.write_text(text, encoding="utf-8")
    for path in target.rglob("*.java"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        text = text.replace("examplemod", mod_id).replace("Example Mod", mod_name)
        path.write_text(text, encoding="utf-8")
