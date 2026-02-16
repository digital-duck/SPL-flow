# SPL-Flow — Feature TODO

## `splflow models` — OpenRouter model search

**Problem**: Finding the exact model ID string for `--models` requires manually browsing openrouter.ai.

**Feature**: Add a `splflow models` subcommand that queries the OpenRouter `/models` endpoint and filters results by keyword — so users can search without leaving the terminal.

```bash
# Search by keyword (case-insensitive, matches id, name, or description)
splflow models claude
splflow models gemini
splflow models "mistral 7b"

# Example output
splflow models sonnet

  anthropic/claude-sonnet-4-5          Claude Sonnet 4.5         $3.00 / $15.00 per M tokens
  anthropic/claude-sonnet-4-5-20250929 Claude Sonnet 4.5 (snap)  $3.00 / $15.00 per M tokens
```

**Implementation sketch**:
- New `splflow models [KEYWORD]` command in `src/cli.py`
- `GET https://openrouter.ai/api/v1/models` (no auth required for listing)
- Filter rows where `KEYWORD` appears in `id`, `name`, or `description` (case-insensitive)
- Display: `id`, `name`, `pricing.prompt` / `pricing.completion` per M tokens
- `--adapter openrouter` flag (default) so the endpoint URL is consistent with the adapter config
- `--json` flag to dump raw filtered JSON for scripting
