import json
from pathlib import Path
from typing import Any

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
