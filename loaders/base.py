from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Loader:
    name: str
    display_name: str


LOADERS = (
    Loader("forge", "Forge"),
    Loader("fabric", "Fabric"),
    Loader("neoforge", "NeoForge"),
)
