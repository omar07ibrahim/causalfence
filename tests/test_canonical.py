"""Canonical JSON boundary tests."""

from __future__ import annotations

import math

import pytest

from causalfence.canonical import canonical_bytes, parse_json_bytes, sha256_value
from causalfence.errors import ContractError


def test_canonical_order_is_stable() -> None:
    assert canonical_bytes({"b": 2, "a": 1}) == b'{"a":1,"b":2}'


def test_digest_ignores_mapping_insertion_order() -> None:
    assert sha256_value({"a": 1, "b": 2}) == sha256_value({"b": 2, "a": 1})


def test_duplicate_json_key_is_rejected() -> None:
    with pytest.raises(ContractError, match="duplicate JSON key"):
        parse_json_bytes(b'{"a":1,"a":2}', max_bytes=100)


def test_invalid_utf8_is_rejected() -> None:
    with pytest.raises(ContractError, match="UTF-8"):
        parse_json_bytes(b"\xff", max_bytes=100)


def test_invalid_json_is_rejected() -> None:
    with pytest.raises(ContractError, match="invalid JSON"):
        parse_json_bytes(b"{", max_bytes=100)


def test_oversized_json_is_rejected_before_parse() -> None:
    with pytest.raises(ContractError, match="exceeds"):
        parse_json_bytes(b"{} ", max_bytes=2)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_values_are_not_canonical(value: float) -> None:
    with pytest.raises(ContractError, match="canonical JSON"):
        canonical_bytes({"value": value})


def test_non_json_object_is_rejected() -> None:
    with pytest.raises(ContractError, match="canonical JSON"):
        canonical_bytes({"bad": {1, 2}})
