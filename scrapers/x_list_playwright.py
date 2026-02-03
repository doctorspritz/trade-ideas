import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright


def normalize_list_url(list_id_or_url: str) -> str:
    if list_id_or_url.startswith("http"):
        return list_id_or_url
    return f"https://x.com/i/lists/{list_id_or_url}"


def parse_post_id(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"/status/(\\d+)", url)
    return match.group(1) if match else None


def load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text(encoding="utf-8"))


def save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def write_jsonl(out_path: Path, rows: list[dict]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def login(storage_state_path: Path, headless: bool) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://x.com/login", wait_until="domcontentloaded")
        input("Log in, then press Enter here to save session state...")
        context.storage_state(path=str(storage_state_path))
        context.close()
        browser.close()


def scrape_list(
    list_url: str,
    storage_state_path: Path,
    out_path: Path,
    state_path: Path,
    max_posts: int,
    max_scrolls: int,
    headless: bool,
    slow_mo: int,
) -> None:
    state = load_state(state_path)
    since_id = state.get("since_id")
    seen = set()
    rows: list[dict] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = browser.new_context(storage_state=str(storage_state_path))
        page = context.new_page()
        page.goto(list_url, wait_until="domcontentloaded")
        page.wait_for_selector('article[data-testid="tweet"]', timeout=60000)

        newest_id = since_id
        scrolls = 0

        while len(rows) < max_posts and scrolls < max_scrolls:
            articles = page.locator('article[data-testid="tweet"]')
            for idx in range(articles.count()):
                article = articles.nth(idx)
                link = article.locator("a[href*='/status/']").first
                href = link.get_attribute("href") if link else None
                url = f"https://x.com{href}" if href and href.startswith("/") else href
                post_id = parse_post_id(url)
                if not post_id or post_id in seen:
                    continue
                if since_id and int(post_id) <= int(since_id):
                    continue

                text_locator = article.locator("div[data-testid='tweetText']")
                text = text_locator.inner_text() if text_locator.count() else ""
                time_locator = article.locator("time")
                created_at = time_locator.get_attribute("datetime") if time_locator.count() else None
                username = None
                if url:
                    match = re.search(r"x\\.com/([^/]+)/status", url)
                    username = match.group(1) if match else None

                row = {
                    "post_id": post_id,
                    "url": url,
                    "username": username,
                    "text": text,
                    "created_at": created_at,
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "list_url": list_url,
                }
                rows.append(row)
                seen.add(post_id)

                if newest_id is None or int(post_id) > int(newest_id):
                    newest_id = post_id

                if len(rows) >= max_posts:
                    break

            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(1200)
            scrolls += 1

        context.close()
        browser.close()

    if rows:
        write_jsonl(out_path, rows)
        state.update({"since_id": newest_id, "last_run": datetime.now(timezone.utc).isoformat()})
        save_state(state_path, state)

    print(f"Captured {len(rows)} posts.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Playwright list scraper (test-only).")
    parser.add_argument("--list-id", help="X list ID (preferred).")
    parser.add_argument("--list-url", help="Full list URL (optional override).")
    parser.add_argument("--login", action="store_true", help="Run interactive login to save session.")
    parser.add_argument("--max-posts", type=int, default=50)
    parser.add_argument("--max-scrolls", type=int, default=8)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=0)
    parser.add_argument("--storage-state", default=".runtime/x_storage_state.json")
    parser.add_argument("--out", default="data/x_posts.jsonl")
    parser.add_argument("--state", default="data/x_scrape_state.json")
    args = parser.parse_args()

    storage_state_path = Path(args.storage_state)

    if args.login:
        login(storage_state_path=storage_state_path, headless=False)
        return

    list_id_or_url = args.list_url or args.list_id or os.environ.get("X_LIST_ID")
    if not list_id_or_url:
        raise SystemExit("Provide --list-id or --list-url (or set X_LIST_ID).")

    list_url = normalize_list_url(list_id_or_url)

    if not storage_state_path.exists():
        raise SystemExit("Storage state missing. Run with --login first.")

    scrape_list(
        list_url=list_url,
        storage_state_path=storage_state_path,
        out_path=Path(args.out),
        state_path=Path(args.state),
        max_posts=args.max_posts,
        max_scrolls=args.max_scrolls,
        headless=args.headless,
        slow_mo=args.slow_mo,
    )


if __name__ == "__main__":
    main()
