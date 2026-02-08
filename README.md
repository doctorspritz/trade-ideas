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

   Add accounts to a list (best-effort UI automation):
   ```bash
   # Option A: pass list id/url directly
   python scrapers/x_list_playwright.py --list-id YOUR_LIST_ID --add-members --members @foo @bar

   # Option B: use an alias env var, e.g. X_LIST_ID_2UK
   X_LIST_ID_2UK=YOUR_LIST_ID python scrapers/x_list_playwright.py --list-alias 2uk --add-members --members @foo @bar
   ```
4. Run the v0 pipeline:
   ```bash
   # OpenAI
   OPENAI_API_KEY=... python -m v0.run --input data/x_posts.jsonl --digest-out digest.md

   # OpenRouter
   OPENROUTER_API_KEY=... python -m v0.run --input data/x_posts.jsonl --digest-out digest.md
   ```

Output: `digest.md` in the repo root.
