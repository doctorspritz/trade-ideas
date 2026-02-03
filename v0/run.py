import argparse
from pathlib import Path

from v0.db import connect, init_db
from v0.digest import write_digest
from v0.pipeline import ingest_jsonl, process_posts


def main() -> None:
    parser = argparse.ArgumentParser(description="Run v0 trade-ideas pipeline.")
    parser.add_argument("--input", default="data/x_posts.jsonl", help="Input JSONL file.")
    parser.add_argument("--db", default="data/alpha.db", help="SQLite DB path.")
    parser.add_argument("--prompt-dir", default="prompts", help="Prompt directory.")
    parser.add_argument("--schema-dir", default="schemas", help="Schema directory.")
    parser.add_argument("--gatekeeper-model", default="gpt-4o-mini")
    parser.add_argument("--analyst-model", default="gpt-4o-mini")
    parser.add_argument("--digest-hours", type=int, default=12)
    parser.add_argument("--digest-out", default="digest.md")
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--skip-llm", action="store_true")
    args = parser.parse_args()

    conn = connect(args.db)
    init_db(conn)

    if not args.skip_ingest:
        inserted = ingest_jsonl(conn, Path(args.input))
        print(f"Inserted {inserted} posts.")

    if not args.skip_llm:
        processed = process_posts(
            conn,
            model_gatekeeper=args.gatekeeper_model,
            model_analyst=args.analyst_model,
            prompt_dir=Path(args.prompt_dir),
            schema_dir=Path(args.schema_dir),
        )
        print(f"Processed {processed} posts with LLM.")

    write_digest(args.digest_out, hours=args.digest_hours)
    print(f"Wrote digest to {args.digest_out}.")


if __name__ == "__main__":
    main()
