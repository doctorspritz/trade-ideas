import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from v0.db import connect, init_db


def make_digest(hours: int = 12) -> str:
    conn = connect()
    init_db(conn)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    rows = conn.execute(
        """
        SELECT raw_posts.post_id,
               raw_posts.username,
               raw_posts.created_at,
               raw_posts.scraped_at,
               raw_posts.alpha_json
        FROM raw_posts
        WHERE raw_posts.alpha_json IS NOT NULL
          AND COALESCE(raw_posts.created_at, raw_posts.scraped_at) >= ?
        ORDER BY raw_posts.created_at DESC
        """,
        (cutoff,),
    ).fetchall()

    by_asset: dict[str, list[tuple[dict, dict]]] = defaultdict(list)

    for row in rows:
        alpha = json.loads(row["alpha_json"])
        assets = alpha.get("assets") or ["(unmapped)"]
        for asset in assets:
            by_asset[asset].append((row, alpha))

    lines = [f"# Digest (last {hours}h)", ""]

    for asset, items in sorted(by_asset.items(), key=lambda kv: len(kv[1]), reverse=True):
        stances = defaultdict(int)
        for _, alpha in items:
            stances[alpha.get("stance", "unclear")] += 1

        stance_text = ", ".join([f\"{k}:{v}\" for k, v in stances.items()])
        lines.append(f"## {asset} — {stance_text}")
        lines.append("")

        for row, alpha in items[:5]:
            username = row["username"]
            url = f"https://x.com/{username}/status/{row['post_id']}" if username else f\"(post {row['post_id']})\"
            lines.append(f"- {url}")
            for bullet in (alpha.get("rationale_bullets") or [])[:3]:
                lines.append(f"  - {bullet}")
            evidence = alpha.get("evidence", {})
            for link in (evidence.get("links") or [])[:3]:
                lines.append(f"  - link: {link.get('url')}")
        lines.append("")

    return "\n".join(lines)


def write_digest(path: str, hours: int) -> None:
    digest = make_digest(hours=hours)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(digest)
