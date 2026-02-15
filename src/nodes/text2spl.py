"""Text2SPL Node: translates free-form user query to SPL syntax."""
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

        adapter = get_adapter("claude_cli")
        prompt = get_text2spl_prompt(
            prep_res["user_input"],
            prep_res["context_text"],
            prep_res["error"],
            retrieved_examples=retrieved_examples,
        )
        _log.debug("Text2SPL prompt length: %d chars", len(prompt))
        result = asyncio.run(adapter.generate(
            prompt=prompt,
            model="",
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
        # Strip markdown code fences if LLM wrapped output in ```sql ... ```
        spl = exec_res
        if spl.startswith("```"):
            lines = spl.split("\n")
            end = -1 if lines[-1].strip() == "```" else len(lines)
            spl = "\n".join(lines[1:end])
        shared["spl_query"] = spl.strip()
        shared["retry_count"] = prep_res["retry_count"] + 1
        _log.info("Text2SPL done  spl_lines=%d  total_attempts=%d",
                  len(spl.strip().splitlines()), shared["retry_count"])
        return "validate"
