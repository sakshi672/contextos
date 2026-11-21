"""Narrow cloud model adapter. No memory leaves the server without account opt-in."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

EMBEDDING_MODEL = "text-embedding-3-small"
ANSWER_MODEL = "gpt-6.1-terra"
EMBEDDING_DIMENSIONS = 1536


class ProviderError(Exception):
    pass


def configured() -> bool:
    return bool(os.environ.get("CONTEXT_OS_OPENAI_API_KEY", "").strip())


def post(path: str, payload: dict) -> dict:
    key = os.environ.get("CONTEXT_OS_OPENAI_API_KEY", "").strip()
    if not key:
        raise ProviderError("AI provider is not configured on this server")
    request = Request("https://api.openai.com/v1/" + path,
                      data=json.dumps(payload).encode("utf-8"), method="POST",
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=40) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise ProviderError("AI provider request failed") from exc


def embed(text: str) -> tuple[list[float], int]:
    data = post("embeddings", {"model": EMBEDDING_MODEL, "input": text,
                               "encoding_format": "float", "dimensions": EMBEDDING_DIMENSIONS})
    try:
        vector = data["data"][0]["embedding"]
        tokens = data["usage"]["total_tokens"]
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError("Unexpected embedding dimensions")
        return vector, tokens
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError("AI provider returned an invalid embedding") from exc


def generate(instructions: str, prompt: str, schema: dict, max_output_tokens: int = 1200) -> tuple[dict, int, int]:
    data = post("responses", {"model": ANSWER_MODEL, "instructions": instructions,
                              "input": prompt, "store": False, "max_output_tokens": max_output_tokens,
                              "text": {"format": {"type": "json_schema", "name": "grounded_answer",
                                                  "schema": schema, "strict": True}}})
    try:
        if data["status"] != "completed":
            raise ValueError("Incomplete response")
        parts = [part["text"] for item in data["output"] if item.get("type") == "message"
                 for part in item.get("content", []) if part.get("type") == "output_text"]
        result = json.loads("".join(parts))
        return result, data["usage"]["input_tokens"], data["usage"]["output_tokens"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError("AI provider returned an invalid answer") from exc
