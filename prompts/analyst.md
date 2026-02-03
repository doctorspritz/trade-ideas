# Analyst Extraction Prompt

Extract a trade‑idea object from the post text. Output JSON that matches the
AlphaObjectV2 schema exactly.

## Rules

- **Do not infer** assets, levels, or catalysts that are not explicit.
- If entry/stop/targets are missing, set them to null/empty and add an item to
  `ambiguities`.
- If stance is not explicit, set `stance` to `unclear`.
- Keep `rationale_bullets` concise (max 5).
- `evidence.links` should include URLs that appear in the post. Use `type=null`
  if the link type is unclear.
- Use `asset_class_tag=null` and `time_decay_half_life=null` when unknown.
- Always include `origin.post_id` and `origin.post_url` if available in input.

## Output

Return only valid JSON that conforms to the schema.
