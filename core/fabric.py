from __future__ import annotations

import json
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from core.app import cache_get, cache_set, load_config
from core.retry import with_retry

FABRIC_META = "https://meta.fabricmc.net/v2"
FABRIC_TEMPLATE_REPO = "https://github.com/FabricMC/fabric-example-mod"
USER_AGENT = "MDK-Manager/3.0"


class FabricError(RuntimeError):
    pass


@dataclass(frozen=True)
class FabricTemplate:
    minecraft: str
    loader: str
    loom: str
    fabric_api: str | None
    branch: str
    archive_url: str


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
        raise FabricError(f"Serwer Fabric zwrócił HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise FabricError(f"Nie można połączyć się z Fabric: {exc.reason}") from exc
    except TimeoutError as exc:
        raise FabricError("Przekroczono czas połączenia z Fabric.") from exc


def fetch_json(url: str):
    with _open_url(url) as response:
        try:
            return json.loads(response.read().decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise FabricError("Fabric zwrócił niepoprawną odpowiedź JSON.") from exc


def fetch_text(url: str) -> str:
    with _open_url(url) as response:
        return response.read().decode("utf-8", errors="replace")


def get_supported_minecraft_versions() -> list[str]:
    config = load_config()
    if config.get("cache_enabled", True):
        cached = cache_get("fabric_minecraft_versions", int(config.get("cache_ttl_hours", 12)))
        if isinstance(cached, list) and cached:
            return cached
    data = with_retry(lambda: fetch_json(f"{FABRIC_META}/versions/game"), attempts=int(config.get("download_retries", 3)))
    versions = [item["version"] for item in data if item.get("stable", True)]
    if not versions:
        raise FabricError("Nie udało się odczytać listy wersji Minecraft z Fabric.")
    result = sorted(set(versions), key=_version_key, reverse=True)
    if config.get("cache_enabled", True):
        cache_set("fabric_minecraft_versions", result)
    return result


def get_loader_versions(minecraft_version: str) -> list[str]:
    config = load_config()
    key = f"fabric_loaders_{minecraft_version}"
    if config.get("cache_enabled", True):
        cached = cache_get(key, int(config.get("cache_ttl_hours", 12)))
        if isinstance(cached, list) and cached:
            return cached
    data = with_retry(lambda: fetch_json(f"{FABRIC_META}/versions/loader/{minecraft_version}"), attempts=int(config.get("download_retries", 3)))
    versions = [item["loader"]["version"] for item in data if item.get("loader", {}).get("version")]
    if not versions:
        raise FabricError(f"Brak wersji Fabric Loader dla Minecraft {minecraft_version}.")
    if config.get("cache_enabled", True):
        cache_set(key, versions)
    return versions


def _parse_properties(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _template_archive(branch: str) -> bytes:
    url = f"{FABRIC_TEMPLATE_REPO}/archive/refs/heads/{urllib.parse.quote(branch, safe='')}.zip"
    with _open_url(url, timeout=60) as response:
        return response.read()


def _find_template_archive(minecraft_version: str) -> tuple[str, bytes]:
    candidates = [minecraft_version]
    if minecraft_version.startswith("1."):
        candidates.append(minecraft_version.rsplit(".", 1)[0])
    last_error: Exception | None = None
    for branch in dict.fromkeys(candidates):
        try:
            return branch, _template_archive(branch)
        except FabricError as exc:
            last_error = exc
            if "HTTP 404" not in str(exc):
                raise
    raise FabricError(f"Nie znaleziono oficjalnego template Fabric dla Minecraft {minecraft_version}.") from last_error


def get_template(minecraft_version: str) -> FabricTemplate:
    branch, archive = _find_template_archive(minecraft_version)
    with zipfile.ZipFile(__import__("io").BytesIO(archive)) as zf:
        properties_name = next((name for name in zf.namelist() if name.count("/") == 1 and name.endswith("/gradle.properties")), None)
        if not properties_name:
            raise FabricError("Template Fabric nie zawiera gradle.properties.")
        properties = _parse_properties(zf.read(properties_name).decode("utf-8", errors="replace"))
    template_minecraft = properties.get("minecraft_version")
    loader = properties.get("loader_version")
    loom = properties.get("loom_version")
    fabric_api = properties.get("fabric_api_version")
    if not template_minecraft or not loader or not loom:
        raise FabricError("Nie udało się odczytać wersji Minecraft/Loader/Loom z template Fabric.")
    if template_minecraft != minecraft_version:
        raise FabricError(f"Template Fabric '{branch}' jest dla Minecraft {template_minecraft}, a wybrano {minecraft_version}.")
    available_loaders = get_loader_versions(minecraft_version)
    if loader not in available_loaders:
        loader = available_loaders[0]
    return FabricTemplate(template_minecraft, loader, loom, fabric_api, branch,
                          f"{FABRIC_TEMPLATE_REPO}/archive/refs/heads/{urllib.parse.quote(branch, safe='')}.zip")


def _safe_member_path(root: Path, member: str) -> Path:
    target = (root / member).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise FabricError(f"Niebezpieczna ścieżka w template: {member}")
    return target


def create_project(template: FabricTemplate, target: Path, mod_name: str, mod_id: str | None = None) -> None:
    target = target.expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise FabricError(f"Katalog już istnieje i nie jest pusty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    mod_id = mod_id or re.sub(r"[^a-z0-9_-]+", "-", mod_name.lower()).strip("-_")
    if not mod_id:
        raise FabricError("Nie udało się utworzyć poprawnego Mod ID z nazwy moda.")
    archive = _template_archive(template.branch)
    with zipfile.ZipFile(__import__("io").BytesIO(archive)) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        prefix = template.branch + "/"
        if not any(m.filename.startswith(prefix) for m in members):
            roots = {m.filename.split("/", 1)[0] for m in members if "/" in m.filename}
            if len(roots) != 1:
                raise FabricError("Nie udało się ustalić katalogu głównego template Fabric.")
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


def _replace_project_metadata(target: Path, mod_name: str, mod_id: str, template: FabricTemplate) -> None:
    properties_path = target / "gradle.properties"
    if properties_path.exists():
        text = properties_path.read_text(encoding="utf-8")
        text = re.sub(r"(?m)^minecraft_version=.*$", f"minecraft_version={template.minecraft}", text)
        text = re.sub(r"(?m)^loader_version=.*$", f"loader_version={template.loader}", text)
        text = re.sub(r"(?m)^loom_version=.*$", f"loom_version={template.loom}", text)
        properties_path.write_text(text, encoding="utf-8")
    settings = target / "settings.gradle"
    if settings.exists():
        text = settings.read_text(encoding="utf-8")
        text = re.sub(r"rootProject\.name\s*=\s*['\"][^'\"]+['\"]", f"rootProject.name = '{mod_id}'", text)
        settings.write_text(text, encoding="utf-8")
    fabric_mod = target / "src" / "main" / "resources" / "fabric.mod.json"
    if fabric_mod.exists():
        try:
            data = json.loads(fabric_mod.read_text(encoding="utf-8"))
            data["id"] = mod_id
            data["name"] = mod_name
            fabric_mod.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except json.JSONDecodeError as exc:
            raise FabricError("Template zawiera niepoprawny fabric.mod.json.") from exc
    gradle_properties = target / "gradle.properties"
    if gradle_properties.exists():
        text = gradle_properties.read_text(encoding="utf-8")
        text = re.sub(r"(?m)^maven_group=.*$", "maven_group=com.example", text)
        text = re.sub(r"(?m)^archives_base_name=.*$", f"archives_base_name={mod_id}", text)
        text = re.sub(r"(?m)^archive_base_name=.*$", f"archive_base_name={mod_id}", text)
        gradle_properties.write_text(text, encoding="utf-8")
