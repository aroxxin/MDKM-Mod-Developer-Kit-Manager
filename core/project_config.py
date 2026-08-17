from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

IGNORED_DIRS = {".git", ".gradle", "build", "out", ".idea", "__pycache__"}
TEXT_EXTENSIONS = {".java", ".kt", ".kts", ".json", ".toml", ".properties", ".gradle", ".groovy", ".xml", ".yml", ".yaml", ".txt", ".md", ".mcmeta", ".cfg", ".conf", ".mixins"}
TEXT_FILENAMES = {"gradle.properties", "settings.gradle", "settings.gradle.kts", "fabric.mod.json", "mods.toml", "neoforge.mods.toml"}


class ProjectConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectInfo:
    path: Path
    loader: str
    mod_id: str


@dataclass(frozen=True)
class Change:
    kind: str
    old: str
    new: str
    path: Path


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _candidate_from_properties(path: Path, key: str) -> str | None:
    text = _read_text(path)
    if text is None:
        return None
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*([^#\r\n]+)", text)
    return match.group(1).strip() if match else None


def detect_project(root: Path) -> ProjectInfo:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ProjectConfigError(f"Katalog projektu nie istnieje: {root}")

    fabric = root / "src/main/resources/fabric.mod.json"
    if fabric.exists():
        try:
            data = json.loads(fabric.read_text(encoding="utf-8"))
            mod_id = str(data.get("id", "")).strip()
            if mod_id:
                return ProjectInfo(root, "fabric", mod_id)
        except (OSError, json.JSONDecodeError):
            pass

    neo = root / "gradle.properties"
    neo_id = _candidate_from_properties(neo, "mod_id")
    neo_meta = root / "src/main/resources/META-INF/neoforge.mods.toml"
    if neo_id or neo_meta.exists():
        if neo_id:
            return ProjectInfo(root, "neoforge", neo_id)
        text = _read_text(neo_meta) or ""
        match = re.search(r"(?m)^\s*modId\s*=\s*[\"']([^\"']+)", text)
        if match:
            return ProjectInfo(root, "neoforge", match.group(1))

    forge_meta = root / "src/main/resources/META-INF/mods.toml"
    if forge_meta.exists():
        text = _read_text(forge_meta) or ""
        match = re.search(r"(?m)^\s*modId\s*=\s*[\"']([^\"']+)", text)
        if match:
            return ProjectInfo(root, "forge", match.group(1))

    for path in _iter_files(root):
        text = _read_text(path)
        if text is None:
            continue
        match = re.search(r"@Mod\(\s*[\"']([^\"']+)[\"']\s*\)", text)
        if match:
            return ProjectInfo(root, "forge", match.group(1))

    raise ProjectConfigError("Nie udało się rozpoznać loadera ani Mod ID projektu.")


def validate_mod_id(loader: str, mod_id: str) -> tuple[bool, str]:
    if loader == "forge":
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", mod_id):
            return False, "Forge: ID musi pasować do [a-z][a-z0-9_]{1,63}."
    elif loader == "neoforge":
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", mod_id):
            return False, "NeoForge: ID musi pasować do [a-z][a-z0-9_]{1,63}."
    elif loader == "fabric":
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,63}", mod_id):
            return False, "Fabric: ID musi zaczynać się literą i mieć 2-64 znaki [A-Za-z0-9_-]."
    else:
        return False, "Nieznany loader projektu."
    return True, "OK"


def scan_changes(root: Path, old_id: str, new_id: str) -> list[Change]:
    changes: list[Change] = []
    for path in _iter_files(root):
        text = _read_text(path)
        if text is not None and old_id in text:
            changes.append(Change("content", old_id, new_id, path.relative_to(root)))
    for path in _iter_files(root):
        rel = path.relative_to(root)
        if old_id in str(rel):
            changes.append(Change("path", old_id, new_id, rel))
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not path.is_dir() or path == root:
            continue
        rel = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if old_id in str(rel):
            changes.append(Change("path", old_id, new_id, rel))
    unique: dict[tuple[str, str], Change] = {}
    for change in changes:
        unique[(change.kind, str(change.path))] = change
    return sorted(unique.values(), key=lambda c: (str(c.path), c.kind))


def _backup(root: Path) -> Path:
    backup_dir = root / ".mdk-manager" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("before-modid-change-%Y%m%d-%H%M%S")
    archive = backup_dir / f"{stamp}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in _iter_files(root):
            rel = path.relative_to(root)
            if rel.parts[:2] == (".mdk-manager", "backups"):
                continue
            zf.write(path, rel)
    return archive


def apply_mod_id_change(root: Path, old_id: str, new_id: str) -> tuple[Path, list[Change], int]:
    if old_id == new_id:
        raise ProjectConfigError("Nowy Mod ID jest taki sam jak obecny.")
    info = detect_project(root)
    if info.mod_id != old_id:
        raise ProjectConfigError(f"Projekt ma obecnie Mod ID '{info.mod_id}', a oczekiwano '{old_id}'.")
    valid, message = validate_mod_id(info.loader, new_id)
    if not valid:
        raise ProjectConfigError(message)
    changes = scan_changes(root, old_id, new_id)
    if not changes:
        raise ProjectConfigError("Nie znaleziono żadnych wystąpień starego Mod ID.")
    backup = _backup(root)
    changed_files = 0
    for change in changes:
        if change.kind != "content":
            continue
        path = root / change.path
        text = _read_text(path)
        if text is None or old_id not in text:
            continue
        path.write_text(text.replace(old_id, new_id), encoding="utf-8")
        changed_files += 1
    directories = []
    for path in root.rglob("*"):
        if not path.is_dir() or path == root:
            continue
        rel = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if old_id in str(rel):
            directories.append(path)
    for current in sorted(directories, key=lambda p: len(p.relative_to(root).parts)):
        rel = current.relative_to(root)
        destination = root / Path(str(rel).replace(old_id, new_id))
        if destination == current:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ProjectConfigError(f"Nie można zmienić nazwy: cel już istnieje: {destination.relative_to(root)}")
        current.rename(destination)
    files_to_rename = []
    for current in _iter_files(root):
        rel = current.relative_to(root)
        if old_id in str(rel):
            files_to_rename.append(current)
    for current in sorted(files_to_rename, key=lambda p: len(p.relative_to(root).parts), reverse=True):
        rel = current.relative_to(root)
        destination = root / Path(str(rel).replace(old_id, new_id))
        if destination == current:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ProjectConfigError(f"Nie można zmienić nazwy: cel już istnieje: {destination.relative_to(root)}")
        current.rename(destination)
    remaining = scan_changes(root, old_id, new_id)
    if remaining:
        raise ProjectConfigError(f"Migracja została wykonana częściowo, ale znaleziono pozostałe odniesienia do '{old_id}'. Backup: {backup}")
    return backup, changes, changed_files
