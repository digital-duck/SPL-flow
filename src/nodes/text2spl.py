"""Text2SPL Node: translates free-form user query to SPL syntax."""
import re
import sys
import asyncio
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")

from pocketflow import Node
from spl.adapters import get_adapter
from src.utils.spl_templates import get_text2spl_prompt
from src.utils.logging_config import get_logger

_log = get_logger("nodes.text2spl")


class Text2SPLNode(Node):
    """Calls LLM to translate natural language query to SPL syntax.

    shared store reads:  user_input, context_text, last_parse_error, retry_count
    shared store writes: spl_query, retry_count
    actions returned:    "validate"
    """

    def prep(self, shared):
        return {
            "user_input": shared["user_input"],
            "context_text": shared.get("context_text", ""),
            "error": shared.get("last_parse_error", ""),
            "retry_count": shared.get("retry_count", 0),
            "adapter": shared.get("adapter", "openrouter"),
            "selected_model_id": shared.get("selected_model_id", ""),
            "selected_provider": shared.get("selected_provider", ""),
        }

    def exec(self, prep_res):
        attempt = prep_res["retry_count"] + 1
        _log.info(
            "Text2SPL attempt=%d  query_len=%d  context_len=%d  has_error=%s",
            attempt,
            len(prep_res["user_input"]),
            len(prep_res["context_text"]),
            bool(prep_res["error"]),
        )
        if prep_res["error"]:
            _log.debug("retry context (parse error): %s", prep_res["error"])

        # ── RAG retrieval: fetch similar (query, SPL) pairs as few-shot context
        retrieved_examples: list[dict] = []
        try:
            from src.rag.factory import get_store
            store = get_store("chroma")
            records = store.search(prep_res["user_input"], k=5)
            retrieved_examples = [
                {"nl_query": r.nl_query, "spl_query": r.spl_query}
                for r in records
            ]
            _log.info("RAG retrieval  hits=%d", len(retrieved_examples))
        except Exception:
            _log.debug("RAG retrieval unavailable — using static examples only")

        # Use the adapter chosen by the user (sidebar / CLI) for Text2SPL too.
        # For ollama, default to qwen2.5 when no specific model is selected.
        # qwen3 is avoided here: its thinking mode leaks <think>...</think> tags
        # into the content field (both /api/chat and /v1/chat/completions) and
        # produces verbose, hard-to-parse output even with /no_think suppression.
        # qwen2.5 generates clean structured output with no thinking overhead.
        text2spl_adapter_name = prep_res["adapter"]
        text2spl_adapter = get_adapter(text2spl_adapter_name)
        _sid = (prep_res.get("selected_model_id") or "").strip()
        if _sid:
            text2spl_model = _sid
        elif text2spl_adapter_name == "ollama":
            text2spl_model = "qwen2.5"
        else:
            text2spl_model = ""   # adapter default (openrouter auto-routes; claude_cli has one model)

        _log.info(
            "Text2SPL using adapter=%s  model=%s",
            text2spl_adapter_name, text2spl_model or "(adapter default)",
        )

        prompt = get_text2spl_prompt(
            prep_res["user_input"],
            prep_res["context_text"],
            prep_res["error"],
            retrieved_examples=retrieved_examples,
            adapter=prep_res["adapter"],
            selected_model_id=prep_res["selected_model_id"],
            selected_provider=prep_res["selected_provider"],
        )
        _log.debug("Text2SPL prompt length: %d chars", len(prompt))
        result = asyncio.run(text2spl_adapter.generate(
            prompt=prompt,
            model=text2spl_model,
            max_tokens=2000,
            temperature=0.2,
            system=(
                "You are an expert SPL (Structured Prompt Language) code generator. "
                "Output ONLY valid SPL code, no explanation, no markdown code fences."
            ),
        ))
        _log.debug("Text2SPL raw output:\n%s", result.content)
        return result.content.strip()

    def post(self, shared, prep_res, exec_res):
        spl = exec_res

        # Strip <think>…</think> reasoning blocks emitted by thinking models
        # (qwen3, deepseek-r1, etc.) before the SPL reaches the validator.
        # The ollama adapter returns raw content; the lexer chokes on `/` or
        # other characters that appear inside thinking text.
        spl = re.sub(r"<think>.*?</think>", "", spl, flags=re.DOTALL | re.IGNORECASE)
        # Also handle an unclosed <think> block (model output truncated).
        spl = re.sub(r"<think>.*", "", spl, flags=re.DOTALL | re.IGNORECASE)
        spl = spl.strip()

        # Strip markdown code fences if LLM wrapped output in ```sql ... ```
        if spl.startswith("```"):
            lines = spl.split("\n")
            end = -1 if lines[-1].strip() == "```" else len(lines)
            spl = "\n".join(lines[1:end])

        # Replace model names that don't belong to the active adapter with
        # "auto" so the executor can resolve them correctly at runtime.
        # LLMs sometimes hallucinate adapter-incorrect names (e.g. generating
        # "claude-sonnet-4-5" even when the adapter is ollama).
        spl = _sanitize_model_names(spl.strip(), prep_res["adapter"])

        shared["spl_query"] = spl
        shared["retry_count"] = prep_res["retry_count"] + 1
        _log.info("Text2SPL done  spl_lines=%d  total_attempts=%d",
                  len(spl.splitlines()), shared["retry_count"])
        return "validate"


# ── Model-name sanitiser ───────────────────────────────────────────────────────

_USING_MODEL_RE = re.compile(r'(USING\s+MODEL\s+)"([^"]+)"', re.IGNORECASE)


def _sanitize_model_names(spl: str, adapter: str) -> str:
    """Replace adapter-incompatible model names with ``"auto"``.

    The Text2SPL LLM sometimes emits model names it was trained on (e.g.
    ``claude-sonnet-4-5``) even when the active adapter is ``ollama``.
    This function scans every ``USING MODEL "..."`` clause and replaces any
    name that is not in MODEL_CATALOG[adapter] with ``"auto"``, which the
    executor then resolves via the model router.

    ``"auto"`` itself is always kept unchanged.
    """
    from src.utils.model_catalog import MODEL_CATALOG
    valid = set(MODEL_CATALOG.get(adapter, {}).keys())

    def _replace(m: re.Match) -> str:
        prefix, model_name = m.group(1), m.group(2)
        if model_name.lower() == "auto" or model_name in valid:
            return m.group(0)
        _log.info(
            "sanitise: replaced incompatible model %r → auto  (adapter=%s)",
            model_name, adapter,
        )
        return f'{prefix}"auto"'

    return _USING_MODEL_RE.sub(_replace, spl)
