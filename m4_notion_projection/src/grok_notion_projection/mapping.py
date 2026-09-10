"""Versioned property mappings. Projection never invents fields."""
from __future__ import annotations

from typing import Mapping

MAPPING_REGISTRY: dict[int, Mapping[str, str]] = {
    1: {
        "Result Ref": "result_ref",
        "Status": "status",
    }
}


def resolve_mapping(version: int) -> Mapping[str, str]:
    if version not in MAPPING_REGISTRY:
        raise KeyError(version)
    return MAPPING_REGISTRY[version]
