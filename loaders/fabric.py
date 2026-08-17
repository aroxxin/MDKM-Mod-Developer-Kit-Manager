from .base import Loader
from core.fabric import FabricError, FabricTemplate, create_project, get_loader_versions, get_supported_minecraft_versions, get_template

LOADER = Loader("fabric", "Fabric")

__all__ = ["LOADER", "FabricError", "FabricTemplate", "create_project", "get_loader_versions", "get_supported_minecraft_versions", "get_template"]
