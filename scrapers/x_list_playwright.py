import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
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


def _wait_any(page, selectors: list[str], timeout_ms: int = 15000):
    """Wait for the first selector that appears; returns the selector."""
    start = time.time()
    last_err: Exception | None = None
    while (time.time() - start) * 1000 < timeout_ms:
        for sel in selectors:
            try:
                page.wait_for_selector(sel, timeout=750)
                return sel
            except PlaywrightTimeoutError as err:
                last_err = err
                continue
    raise PlaywrightTimeoutError(f"None of selectors appeared: {selectors}. Last error: {last_err}")


def add_members_to_list(
    list_url: str,
    storage_state_path: Path,
    members: list[str],
    headless: bool,
    slow_mo: int,
) -> None:
    """Best-effort UI automation to add members to an X list.

    Notes:
      - X UI changes frequently; this uses multiple selector fallbacks.
      - Requires an authenticated storage_state (run with --login first).
    """

    cleaned = []
    for m in members:
        m = (m or "").strip()
        if not m:
            continue
        cleaned.append(m[1:] if m.startswith("@") else m)

    if not cleaned:
        print("No members provided.")
        return

    # Try to jump straight to the members management surface.
    members_url = list_url.rstrip("/") + "/members"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = browser.new_context(storage_state=str(storage_state_path))
        page = context.new_page()

        page.goto(members_url, wait_until="domcontentloaded")

        # Some accounts land on list timeline first; ensure we can see member UI.
        _wait_any(
            page,
            selectors=[
                'a[href$="/members"]',
                'text=/Members/i',
                'input[placeholder*="Search"]',
            ],
            timeout_ms=60000,
        )

        # Attempt to open the member management dialog/screen.
        # Common flows:
        #   - Members tab has an "Add" / "Add member" button
        #   - Kebab menu -> Manage members
        opened_manage = False
        for attempt in range(3):
            try:
                # If we're not on members page, click it.
                members_tab = page.get_by_role("link", name=re.compile(r"members", re.I))
                if members_tab.count():
                    members_tab.first.click(timeout=3000)

                add_btn = page.get_by_role(
                    "button",
                    name=re.compile(r"add( member)?|add people|add to list", re.I),
                )
                if add_btn.count():
                    add_btn.first.click(timeout=5000)
                    opened_manage = True
                    break

                options_btn = page.get_by_role(
                    "button",
                    name=re.compile(r"list options|more|options", re.I),
                )
                if options_btn.count():
                    options_btn.first.click(timeout=5000)
                    manage_item = page.get_by_role(
                        "menuitem",
                        name=re.compile(r"manage members|edit list", re.I),
                    )
                    if manage_item.count():
                        manage_item.first.click(timeout=5000)
                        opened_manage = True
                        break
            except Exception:
                pass

            page.wait_for_timeout(750)
            if attempt == 2 and not opened_manage:
                print("Warning: couldn't confidently open member management UI; will still try searching inline.")

        # The manage screen usually contains a search box for accounts.
        search_selectors = [
            'input[placeholder*="Search"]',
            'input[aria-label*="Search"]',
            'input[type="text"]',
        ]

        added = 0
        for username in cleaned:
            print(f"Adding @{username}...")
            try:
                # Focus search
                sel = _wait_any(page, search_selectors, timeout_ms=20000)
                page.locator(sel).first.click(timeout=2000)
                page.locator(sel).first.fill("", timeout=2000)
                page.locator(sel).first.type(username, delay=30)

                # Results: click the relevant "Add" button.
                # Heuristic: row containing @username and an Add button.
                row = page.get_by_text(f"@{username}", exact=False).first
                row.wait_for(timeout=10000)

                add_in_row = page.get_by_role("button", name=re.compile(r"add", re.I))
                # Narrow by proximity if possible
                try:
                    container = row.locator("xpath=ancestor::div[1]")
                    btn = container.get_by_role("button", name=re.compile(r"add", re.I))
                    if btn.count():
                        btn.first.click(timeout=5000)
                    else:
                        add_in_row.first.click(timeout=5000)
                except Exception:
                    add_in_row.first.click(timeout=5000)

                added += 1
                page.wait_for_timeout(750)
            except Exception as err:
                print(f"Failed to add @{username}: {err}")

        context.close()
        browser.close()

    print(f"Added {added}/{len(cleaned)} accounts.")


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
    load_dotenv()

    parser = argparse.ArgumentParser(description="Playwright list scraper / list member helper (test-only).")
    parser.add_argument("--list-id", help="X list ID (preferred).")
    parser.add_argument("--list-url", help="Full list URL (optional override).")
    parser.add_argument(
        "--list-alias",
        help="Alias that resolves to env var X_LIST_ID_<ALIAS> (e.g. --list-alias 2uk uses X_LIST_ID_2UK).",
    )
    parser.add_argument("--login", action="store_true", help="Run interactive login to save session.")

    parser.add_argument("--add-members", action="store_true", help="Add accounts to the list (best-effort).")
    parser.add_argument(
        "--members",
        nargs="*",
        default=[],
        help="Usernames to add (e.g. --members @foo @bar).",
    )
    parser.add_argument(
        "--members-file",
        help="Path to newline-separated usernames (optionally with @ prefix).",
    )

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

    list_id_or_url = args.list_url or args.list_id
    if not list_id_or_url and args.list_alias:
        key = f"X_LIST_ID_{args.list_alias.upper()}"
        list_id_or_url = os.environ.get(key)

    list_id_or_url = list_id_or_url or os.environ.get("X_LIST_ID")
    if not list_id_or_url:
        raise SystemExit(
            "Provide --list-id or --list-url (or --list-alias with X_LIST_ID_<ALIAS> set; or set X_LIST_ID)."
        )

    list_url = normalize_list_url(list_id_or_url)

    if not storage_state_path.exists():
        raise SystemExit("Storage state missing. Run with --login first.")

    members = list(args.members or [])
    if args.members_file:
        p = Path(args.members_file)
        members.extend([ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()])

    if args.add_members:
        add_members_to_list(
            list_url=list_url,
            storage_state_path=storage_state_path,
            members=members,
            headless=args.headless,
            slow_mo=args.slow_mo,
        )
        return

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
