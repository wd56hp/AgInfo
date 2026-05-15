"""Load speed table from YAML and map OSM edge data to mph."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional, Union

import yaml

logger = logging.getLogger(__name__)


def load_speed_config(path: Union[str, Path]) -> tuple[dict[str, float], dict[str, Any]]:
    """
    Load road speeds and defaults from YAML.

    Returns
    -------
    speeds_mph : dict
        highway / surface tag -> miles per hour
    extras : dict
        Non-speed keys (e.g. nested ``defaults``) preserved for callers.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Speed config not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw: MutableMapping[str, Any] = yaml.safe_load(f) or {}

    defaults = raw.pop("defaults", {}) or {}
    speeds: dict[str, float] = {}
    for k, v in raw.items():
        if isinstance(v, (int, float)):
            speeds[str(k)] = float(v)

    if "unknown_road" not in speeds:
        speeds["unknown_road"] = 40.0
        logger.warning("unknown_road missing in config; using 40 mph")

    return speeds, {"defaults": defaults}


def unload_minutes_from_config(extras: Mapping[str, Any], override: Optional[float]) -> float:
    if override is not None:
        return float(override)
    d = extras.get("defaults") or {}
    um = d.get("unload_minutes")
    if um is None:
        return 30.0
    return float(um)


def _highway_tokens(highway: Any) -> list[str]:
    if highway is None:
        return []
    if isinstance(highway, list):
        return [str(h).lower() for h in highway if h is not None]
    return [str(highway).lower()]


def _surface_tokens(surface: Any) -> list[str]:
    if surface is None:
        return []
    if isinstance(surface, list):
        return [str(s).lower() for s in surface if s is not None]
    return [str(surface).lower()]


def edge_speed_mph(edge_data: Mapping[str, Any], speeds: Mapping[str, float]) -> float:
    """
    Resolve travel speed (mph) for one OSMnx / NetworkX edge attribute dict.
    """
    hw = _highway_tokens(edge_data.get("highway"))
    for h in hw:
        if h in speeds:
            return speeds[h]

    surf = _surface_tokens(edge_data.get("surface"))
    for s in surf:
        if s in ("dirt", "earth", "ground", "sand"):
            return speeds.get("dirt_road", speeds["unknown_road"])
        if s in ("gravel", "fine_gravel", "compacted"):
            return speeds.get("gravel_road", speeds["unknown_road"])

    if hw:
        logger.debug("Unmapped highway=%s; using unknown_road", hw)
    return speeds["unknown_road"]


def edge_travel_time_minutes(length_m: float, mph: float) -> float:
    if mph <= 0:
        raise ValueError("speed must be positive")
    miles = length_m / 1609.344
    return (miles / mph) * 60.0
