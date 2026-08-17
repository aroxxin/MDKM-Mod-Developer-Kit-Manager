from .base import Loader
from core.forge import ForgeError, ForgeRelease, get_latest_release, get_releases, get_supported_minecraft_versions

LOADER = Loader("forge", "Forge")

__all__ = ["LOADER", "ForgeError", "ForgeRelease", "get_latest_release", "get_releases", "get_supported_minecraft_versions"]
