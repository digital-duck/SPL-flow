"""Text2SPL Node: translates free-form user query to SPL syntax."""
import sys
import asyncio
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")

from pocketflow import Node
from spl.adapters import get_adapter
from src.utils.spl_templates import get_text2spl_prompt


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
        except Exception:
            pass  # silently fall back to static examples only

        adapter = get_adapter("claude_cli")
        prompt = get_text2spl_prompt(
            prep_res["user_input"],
            prep_res["context_text"],
            prep_res["error"],
            retrieved_examples=retrieved_examples,
        )
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
        return "validate"
