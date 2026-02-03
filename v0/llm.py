import json
from pathlib import Path
from typing import Any

import os

from openai import OpenAI


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def structured_call(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_text: str,
    schema: dict[str, Any],
    schema_name: str,
) -> dict[str, Any]:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": f"{system_prompt}\nOutput JSON only."},
            {"role": "user", "content": user_text},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True,
            },
        },
        temperature=0,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty response from model.")
    return json.loads(content)


def build_client() -> OpenAI:
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        headers = {}
        if os.getenv("OPENROUTER_SITE_URL"):
            headers["HTTP-Referer"] = os.getenv("OPENROUTER_SITE_URL")
        if os.getenv("OPENROUTER_APP_NAME"):
            headers["X-Title"] = os.getenv("OPENROUTER_APP_NAME")
        return OpenAI(api_key=openrouter_key, base_url=base_url, default_headers=headers)
    return OpenAI()


def normalize_model_name(model: str) -> str:
    if os.getenv("OPENROUTER_API_KEY") and "/" not in model:
        return f"openai/{model}"
    return model
