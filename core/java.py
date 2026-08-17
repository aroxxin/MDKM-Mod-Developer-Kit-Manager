from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class JavaInfo:
    installed: bool
    version: int | None = None
    raw_version: str | None = None
    executable: str | None = None
    error: str | None = None


def detect_java() -> JavaInfo:
    executable = shutil.which("java")
    if not executable:
        return JavaInfo(installed=False, error="Polecenie java nie zostało znalezione.")

    try:
        result = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = (result.stderr or "") + "\n" + (result.stdout or "")
        match = re.search(r'version "([0-9]+)(?:\.([0-9]+))?', output)
        if not match:
            return JavaInfo(installed=True, executable=executable, error="Nie udało się odczytać wersji Java.")

        major = int(match.group(1))
        if major == 1 and match.group(2):
            major = int(match.group(2))

        raw = match.group(0).split('"')[1]
        return JavaInfo(True, major, raw, executable)
    except (OSError, subprocess.SubprocessError) as exc:
        return JavaInfo(installed=False, executable=executable, error=str(exc))


def required_java_for_minecraft(version: str) -> int:
    """Return the baseline Java required by the Minecraft generation used by Forge."""
    if version.startswith(("26.", "25.", "24.")):
        return 25

    if version.startswith("1."):
        numbers = version.split(".")
        minor = int(numbers[1]) if len(numbers) > 1 and numbers[1].isdigit() else 0
        patch = int(numbers[2]) if len(numbers) > 2 and numbers[2].isdigit() else 0
        if minor >= 20 and patch >= 5:
            return 21
        if minor >= 20:
            return 17
        if minor >= 18:
            return 17
        if minor == 17:
            return 16
        return 8

    return 21


def java_compatible(info: JavaInfo, required: int) -> bool:
    return bool(info.installed and info.version is not None and info.version >= required)
