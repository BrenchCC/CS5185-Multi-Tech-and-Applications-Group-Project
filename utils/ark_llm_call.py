import os
import base64

from volcenginesdkarkruntime import Ark


def _ensure_ark_api_key() -> None:
    """EnsureK LLM_API_KEY is available in environment variables."""
    if not os.environ.get("LLM_API_KEY"):
        raise RuntimeError(
            "Missing LLM_API_KEY in environment. Please export LLM_API_KEY before running."
        )


def call_llm_on_volcengine(input_query, end_point, system_prompt = None, stream = False, reasoning_option = None):
    """Call Ark with input_query, end_point, optional system_prompt, stream and reasoning_option.

    Return reasoning, response text, prompt tokens and completion tokens.
    Raise API errors so the caller can log and bound retries.
    """
    _ensure_ark_api_key()
    client = Ark(
        base_url = os.environ.get("LLM_API_BASE_URL"),
        api_key = os.environ.get("LLM_API_KEY"),
        max_retries = 0,
    )
    try:
        messages = [{"role": "user", "content": input_query}]
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages
        if reasoning_option:
            completion = client.chat.completions.create(
                model = end_point,
                messages = messages,
                timeout = 60,
                stream = stream,
                extra_body = {
                    "thinking": {
                        "type": reasoning_option
                    }
                }
            )
        else:
            completion = client.chat.completions.create(
                model = end_point,
                messages = messages,
                timeout = 60,
                stream = stream
            )
        if stream:
            result = ""
            for tok in completion:
                if not tok.choices:
                    continue
                result += tok.choices[0].delta.content or ""
            return "", result, None, None
        else:
            result = completion.choices[0].message.content
        reasoning_content = getattr(completion.choices[0].message, "reasoning_content", None) or ""
        prompt_tok = getattr(completion.usage, "prompt_tokens", None)
        completion_tok = getattr(completion.usage, "completion_tokens", None)
        if not isinstance(result, str) or not result.strip():
            raise ValueError("Empty LLM response")
        return reasoning_content, result, prompt_tok, completion_tok

    finally:
        client.close()


def call_vision_embedding(image_path, end_point, image_type="jpeg"):
    _ensure_ark_api_key()
    client = Ark()

    # print("----- multimodal embeddings request -----")
    img_bytes = open(image_path, 'rb').read()
    base64_image = base64.b64encode(img_bytes).decode()

    resp = client.multimodal_embeddings.create(
        model=end_point,
        input=[
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{image_type};base64,{base64_image}"
                }
            }
        ]
    )
    try:
        return resp.data["embedding"]
    except Exception as e:
        print("Error: ", e)
        return []
