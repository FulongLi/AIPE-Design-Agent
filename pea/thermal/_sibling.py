"""Locate and import ``heatsink_model`` from the sibling HeatSinkOptimisation checkout (CC BY 4.0)."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

ENV_VAR = "HEATSINK_OPT_DIR"
MODULE_FILE = "heatsink_model.py"
REQUIRED_ATTRIBUTES = ("PlateFinHeatSink", "OperatingPoint", "evaluate", "optimise_pareto", "spreading_resistance")

_cache: ModuleType | None = None


class HeatSinkModelNotFound(ImportError):
    """Raised when the corrected HeatSinkOptimisation module cannot be located or is outdated."""


def candidate_directories() -> list[Path]:
    """Search order: ``$HEATSINK_OPT_DIR`` then ``../HeatSinkOptimisation`` next to this repository."""
    out: list[Path] = []
    env = os.environ.get(ENV_VAR)
    if env:
        out.append(Path(env).expanduser())
    repo_root = Path(__file__).resolve().parents[2]
    out.append(repo_root.parent / "HeatSinkOptimisation")
    return out


def load_heatsink_model(force_reload: bool = False) -> ModuleType:
    """Import and return the sibling ``heatsink_model`` module, with a clear error when absent."""
    global _cache
    if _cache is not None and not force_reload:
        return _cache
    tried: list[str] = []
    for directory in candidate_directories():
        path = directory / MODULE_FILE
        tried.append(str(path))
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("heatsink_model", path)
        if spec is None or spec.loader is None:  # pragma: no cover - defensive
            continue
        module = importlib.util.module_from_spec(spec)
        # dataclasses resolve string annotations through sys.modules[module.__name__] while the
        # class body executes, so the module must be registered before exec_module().
        previous = sys.modules.get("heatsink_model")
        sys.modules["heatsink_model"] = module
        try:
            spec.loader.exec_module(module)
        except ImportError as exc:
            _restore(previous)
            raise HeatSinkModelNotFound(
                f"{path} was found but could not be imported ({exc}); heatsink_model needs numpy and scipy "
                "(pip install -e '.[thermal]')."
            ) from exc
        except Exception:
            _restore(previous)
            raise
        missing = [a for a in REQUIRED_ATTRIBUTES if not hasattr(module, a)]
        if missing:
            _restore(previous)
            raise HeatSinkModelNotFound(
                f"{path} is not the corrected HeatSinkOptimisation 1.0 module (missing {missing}); "
                "update the sibling checkout."
            )
        _cache = module
        return module
    raise HeatSinkModelNotFound(
        "The corrected HeatSinkOptimisation module (heatsink_model.py, CC BY 4.0) was not found. Set the environment "
        f"variable {ENV_VAR} to the HeatSinkOptimisation checkout or place the checkout next to this repository as "
        f"../HeatSinkOptimisation. Paths tried: {tried}"
    )


def _restore(previous: ModuleType | None) -> None:
    if previous is None:
        sys.modules.pop("heatsink_model", None)
    else:
        sys.modules["heatsink_model"] = previous
