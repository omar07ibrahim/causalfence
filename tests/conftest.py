"""Shared deterministic fixture helpers."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).parents[1]
SCENARIO = ROOT / "scenarios" / "multi-region-incident.json"


@pytest.fixture
def incident() -> dict[str, object]:
    return cast(dict[str, object], json.loads(SCENARIO.read_text(encoding="utf-8")))


def cloned(value: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], copy.deepcopy(value))
