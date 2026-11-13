"""AutoTriage ORM models package."""

import importlib
import pkgutil
from pathlib import Path

from app.models.error_log import ErrorLog

# Dynamically import all model modules in this package to register them with Base
for _, module_name, _ in pkgutil.iter_modules([str(Path(__file__).parent)]):
    if module_name not in ("__init__", "schemas"):
        importlib.import_module(f"app.models.{module_name}")

__all__ = ["ErrorLog"]
