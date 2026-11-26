"""Provide bounded Ark parameter selection for a single encoding attempt."""

import os
import sys
import json
import time
import logging
import hashlib
import unicodedata
from pathlib import Path

from dotenv import dotenv_values

sys.path.append(os.getcwd())

from utils.json_extract import extract_json_object

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / "prompts" / "encoding_decision_zh.md"


def llm_decision(payload, audit):
    """Request choices using measured payload and write safe call metadata into audit."""
    started = time.perf_counter()
    try:
        config = dotenv_values(ROOT / ".env", interpolate = False)
        endpoint = os.environ.get("LLM_ENDPOINT", config.get("LLM_ENDPOINT"))
        api_key = os.environ.get("LLM_API_KEY", config.get("LLM_API_KEY"))
        base_url = os.environ.get("LLM_API_BASE_URL", config.get("LLM_API_BASE_URL"))
        base_url = base_url or "https://ark.cn-beijing.volces.com/api/v3"
        if not endpoint or not api_key or api_key in ("xxxxxxxxx", "your-api-key"):
            raise ValueError("Configure LLM_API_KEY and LLM_ENDPOINT before using Ark")
        prompt = PROMPT.read_text(encoding = "utf-8")
        audit["endpoint"] = endpoint
        audit["prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
        audit["request"] = payload

        from volcenginesdkarkruntime import Ark

        # 每轮只请求一次 / A strategy slot permits at most one API request.
        try:
            with Ark(api_key = api_key, base_url = base_url, max_retries = 0) as client:
                result = client.chat.completions.create(
                    model = endpoint,
                    messages = [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": json.dumps(payload, allow_nan = False)},
                    ],
                    timeout = 30,
                    max_tokens = 512,
                )
        except Exception as error:
            audit["api_error_type"] = type(error).__name__
            raise ValueError(f"Ark request failed ({type(error).__name__})") from None

        usage = getattr(result, "usage", None)
        audit["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
        audit["completion_tokens"] = getattr(usage, "completion_tokens", None)
        choices = getattr(result, "choices", None)
        content = choices[0].message.content if choices else None
        decision = extract_json_object(content)
        if set(decision) != {"preset", "aq_mode", "reason"}:
            raise ValueError("Model must return exactly preset, aq_mode and reason")
        if decision["preset"] not in ("medium", "slow"):
            raise ValueError("Invalid model preset")
        if type(decision["aq_mode"]) is not int or decision["aq_mode"] not in (1, 2):
            raise ValueError("Invalid model AQ mode")
        reason = decision["reason"]
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or len(reason) > 600
            or any(unicodedata.category(char).startswith("C") for char in reason)
            or api_key in reason
        ):
            raise ValueError("Invalid model reason")
        audit["validated"] = True
        return {**decision, "method": "llm", "policy_version": audit["prompt_sha256"]}
    finally:
        audit["elapsed_s"] = time.perf_counter() - started
