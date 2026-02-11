import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from v0.db import (
    fetch_unprocessed,
    insert_raw_post,
    text_hash_exists,
    update_alpha,
    update_gatekeeper,
)
from v0.llm import build_client, load_prompt, load_schema, normalize_model_name, structured_call

NOISE_RE = re.compile(
    r"(\\$[A-Za-z]{1,10})|(\\b(long|short|buy|sell|bullish|bearish|puts|calls|"
    r"target|stop|breakout|support|resistance|earnings|cpi|fomc)\\b)|(\\b\\d+(\\.\\d+)?\\b)",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    return re.sub(r"\\s+", " ", text or "").strip().lower()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def stage0_keep(text: str) -> bool:
    return bool(NOISE_RE.search(text)) or ("http" in text)


def ingest_jsonl(conn, jsonl_path: Path) -> int:
    inserted = 0
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            post_id = row.get("post_id") or row.get("id")
            if not post_id:
                continue
            row["post_id"] = post_id
            row["text_hash"] = text_hash(row.get("text", ""))
            row["raw_json"] = json.dumps(row)
            if text_hash_exists(conn, row["text_hash"]):
                continue
            if insert_raw_post(conn, row):
                inserted += 1
    return inserted


def process_posts(
    conn,
    model_gatekeeper: str,
    model_analyst: str,
    prompt_dir: Path,
    schema_dir: Path,
) -> int:
    load_dotenv()
    client = build_client()
    model_gatekeeper = normalize_model_name(model_gatekeeper)
    model_analyst = normalize_model_name(model_analyst)
    gate_prompt = load_prompt(prompt_dir / "gatekeeper.md")
    gate_schema = load_schema(schema_dir / "gatekeeper.schema.json")
    alpha_prompt = load_prompt(prompt_dir / "analyst.md")
    alpha_schema = load_schema(schema_dir / "alpha_object.schema.json")

    processed = 0
    for row in fetch_unprocessed(conn):
        text = row["text"] or ""
        post_id = row["post_id"]
        post_url = row["url"] or ""
        username = row["username"] or ""
        if not stage0_keep(text):
            update_gatekeeper(conn, post_id, {"skipped": True, "reason": "stage0"})
            continue

        gate = structured_call(
            client=client,
            model=model_gatekeeper,
            system_prompt=gate_prompt,
            user_text=text,
            schema=gate_schema,
            schema_name="gatekeeper_result",
        )
        update_gatekeeper(conn, post_id, gate)

        if not (
            gate["is_finance_relevant"]
            and (gate["is_actionable_trade_idea"] or gate["has_media_worth_processing"])
        ):
            continue

        analyst_input = (
            f"POST_ID: {post_id}\nPOST_URL: {post_url}\nUSERNAME: {username}\nTEXT:\n{text}"
        )

        alpha = structured_call(
            client=client,
            model=model_analyst,
            system_prompt=alpha_prompt,
            user_text=analyst_input,
            schema=alpha_schema,
            schema_name="alpha_object_v2",
        )

        alpha = ensure_origin_fields(alpha, post_id, post_url, username)
        alpha = apply_missing_levels_guardrails(alpha, text)
        created_at = (
            row["created_at"] or row["scraped_at"] or datetime.now(timezone.utc).isoformat()
        )
        update_alpha(conn, post_id, alpha, created_at)
        processed += 1

    return processed


def apply_missing_levels_guardrails(alpha: dict[str, Any], text: str) -> dict[str, Any]:
    if not re.search(r"\\b(entry|stop|target|tp|sl)\\b", text, re.IGNORECASE):
        key_levels = alpha.get("key_levels", {})
        key_levels["entry"] = None
        key_levels["invalidation"] = None
        key_levels["targets"] = []
        alpha["key_levels"] = key_levels
        ambiguities = alpha.get("ambiguities", [])
        if "levels not provided" not in ambiguities:
            ambiguities.append("levels not provided")
        alpha["ambiguities"] = ambiguities
    return alpha


def ensure_origin_fields(
    alpha: dict[str, Any], post_id: str, post_url: str, username: str
) -> dict[str, Any]:
    origin = alpha.get("origin") or {}
    origin.setdefault("author_id", None)
    origin["username"] = origin.get("username") or username or None
    origin["post_id"] = origin.get("post_id") or post_id
    origin["post_url"] = origin.get("post_url") or post_url or None
    origin.setdefault("is_retweet_or_repost", False)
    origin.setdefault("is_quote", False)
    origin.setdefault("thread_post_ids", [])
    alpha["origin"] = origin
    return alpha
