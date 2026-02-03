# Trade Ideas

## V0 Demo (Playwright + SQLite)

1. Install deps:
   ```bash
   python -m pip install -r requirements.txt
   python -m playwright install chromium
   ```
2. Log in once to X to save session state:
   ```bash
   python scrapers/x_list_playwright.py --login
   ```
3. Scrape a list into JSONL:
   ```bash
   X_LIST_ID=YOUR_LIST_ID python scrapers/x_list_playwright.py --headless --max-posts 50
   ```
4. Run the v0 pipeline (requires `OPENAI_API_KEY` in env):
   ```bash
   python -m v0.run --input data/x_posts.jsonl --digest-out digest.md
   ```

Output: `digest.md` in the repo root.
