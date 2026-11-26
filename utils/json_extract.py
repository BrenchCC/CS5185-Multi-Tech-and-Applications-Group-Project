"""Extract a bounded JSON object from a model response."""

import re
import json
import math
import logging

logger = logging.getLogger(__name__)

MAX_RESPONSE_CHARS = 16_384


def unique_keys(pairs):
    """Build an object from pairs, rejecting duplicate keys at every level."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    """Reject nonstandard JSON constants such as NaN, represented by value."""
    raise ValueError("Nonstandard JSON number")


def finite_float(value):
    """Parse value as a finite float without accepting exponent overflow."""
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite JSON number")
    return result


def extract_json_object(response):
    """Parse response as one object, optionally wrapped in one Markdown JSON fence."""
    if not isinstance(response, str) or len(response) > MAX_RESPONSE_CHARS:
        raise ValueError("Invalid response type or length")
    payload = response.strip()
    fence = re.fullmatch(r"```(?:json)?[^\S\r\n]*\r?\n(.*?)\r?\n```", payload, re.IGNORECASE | re.DOTALL)
    if fence:
        payload = fence.group(1)
    try:
        result = json.loads(
            payload,
            object_pairs_hook = unique_keys,
            parse_constant = reject_constant,
            parse_float = finite_float
        )
    except (ValueError, RecursionError) as error:
        raise ValueError("Expected exactly one valid JSON object") from error
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")
    return result
