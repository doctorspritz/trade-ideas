#!/usr/bin/env python3
"""Convert bird JSON output to JSONL format expected by v0 pipeline."""

import json
from datetime import datetime, timezone
from pathlib import Path


def convert_bird_tweet(tweet: dict) -> dict:
    """Convert a bird tweet to pipeline format."""
    author = tweet.get("author", {})
    # Don't include the full raw tweet to avoid circular refs
    return {
        "post_id": tweet.get("id"),
        "text": tweet.get("text", ""),
        "url": f"https://x.com/{author.get('username')}/status/{tweet.get('id')}",
        "username": author.get("username"),
        "created_at": tweet.get("createdAt"),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "reply_count": tweet.get("replyCount", 0),
        "retweet_count": tweet.get("retweetCount", 0),
        "like_count": tweet.get("likeCount", 0),
    }


def main():
    input_dir = Path("data")
    output_file = Path("data/x_posts.jsonl")

    all_posts = []
    for json_file in input_dir.glob("*_2026-*.json"):
        print(f"Processing {json_file.name}...")
        with open(json_file) as f:
            content = f.read()
            # Skip info lines at start
            lines = content.split("\n")
            json_start = next(i for i, line in enumerate(lines) if line.strip().startswith("["))
            json_content = "\n".join(lines[json_start:])
            tweets = json.loads(json_content)
            for tweet in tweets:
                all_posts.append(convert_bird_tweet(tweet))

    with open(output_file, "w") as f:
        for post in all_posts:
            f.write(json.dumps(post) + "\n")

    print(f"Wrote {len(all_posts)} posts to {output_file}")


if __name__ == "__main__":
    main()
