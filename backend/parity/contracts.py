"""backend/contracts/ shapes, compared as `catalog/tests/test_contracts.py` does."""

import json
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"


def contract(name: str) -> dict:
    return json.loads((CONTRACTS / f"{name}.json").read_text())


def shape(value):
    """Keys and value types. A `{}` or `[]` says nothing about what it can hold."""
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


def assert_same_shape(actual: dict, name: str, *opaque: str) -> None:
    """`opaque` keys of `data` are free-form JSON owned by the type's author."""
    expected = contract(name)
    actual_data, expected_data = dict(actual["data"]), dict(expected["data"])
    for key in opaque:
        actual_data.pop(key), expected_data.pop(key)
    assert shape({**actual, "data": actual_data}) == shape(
        {**expected, "data": expected_data}
    )
