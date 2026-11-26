"""Security boundaries for model JSON extraction."""

import os
import sys

import pytest

sys.path.append(os.getcwd())

from utils.json_extract import extract_json_object


@pytest.mark.parametrize("raw", [
    '{"preset":"medium","aq_mode":2,"reason":"A brace } in text"}',
    '```json\n{"preset":"medium","aq_mode":2,"reason":"A brace } in text"}\n```',
])
def test_extract_single_object(raw):
    """Accept raw and singly fenced JSON, including a brace inside a string."""
    assert extract_json_object(raw)["aq_mode"] == 2


@pytest.mark.parametrize("raw", [
    '{"x":1,"x":2}',
    '{"x":NaN}',
    '{"x":1e999}',
    '{"x":1} {"x":2}',
    'Commentary {"x":1}',
    '[{"x":1}]',
    'x' * 16_385,
])
def test_reject_invalid_object(raw):
    """Reject ambiguous, unsafe or oversized raw replies before parameter validation."""
    with pytest.raises(ValueError):
        extract_json_object(raw)
