CREATE TABLE IF NOT EXISTS raw_posts (
  post_id TEXT PRIMARY KEY,
  url TEXT,
  username TEXT,
  text TEXT,
  created_at TEXT,
  scraped_at TEXT,
  text_hash TEXT,
  raw_json TEXT,
  gatekeeper_json TEXT,
  alpha_json TEXT,
  processed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_raw_posts_created_at ON raw_posts(created_at);
CREATE INDEX IF NOT EXISTS idx_raw_posts_text_hash ON raw_posts(text_hash);

CREATE TABLE IF NOT EXISTS media (
  post_id TEXT NOT NULL,
  url TEXT NOT NULL,
  type TEXT,
  raw_json TEXT,
  PRIMARY KEY (post_id, url),
  FOREIGN KEY (post_id) REFERENCES raw_posts(post_id)
);

CREATE TABLE IF NOT EXISTS alpha_objects (
  post_id TEXT PRIMARY KEY,
  assets_json TEXT,
  stance TEXT,
  timeframe TEXT,
  extraction_confidence TEXT,
  alpha_json TEXT,
  created_at TEXT,
  FOREIGN KEY (post_id) REFERENCES raw_posts(post_id)
);

CREATE INDEX IF NOT EXISTS idx_alpha_objects_created_at ON alpha_objects(created_at);

CREATE TABLE IF NOT EXISTS narratives (
  narrative_id TEXT PRIMARY KEY,
  title TEXT,
  summary TEXT,
  score REAL,
  created_at TEXT
);
