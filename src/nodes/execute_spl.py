"""ExecuteSPL Node: run the SPL engine against the configured LLM adapter.

Supports USING MODEL auto — when a PROMPT specifies `auto` as its model,
this node resolves it to a concrete model name using the model router before
calling the executor.  Resolution is driven by:
    - task detected from system_role + GENERATE instruction text
    - optional provider preference (e.g. "anthropic", "google")
    - the active adapter ("claude_cli", "openrouter", "ollama")
"""
import sys
import asyncio
from pathlib import Path
sys.path.insert(0, Path.home() / "projects/digital-duck/SPL")

from pocketflow import Node
from spl import parse
from spl.analyzer import Analyzer
from spl.optimizer import Optimizer
from spl.executor import Executor
from spl.ast_nodes import (
    PromptStatement, CreateFunctionStatement,
    SystemRoleCall, CTEClause,
)

from src.utils.model_router import auto_route
from src.utils.logging_config import get_logger

_log = get_logger("nodes.execute")


class ExecuteSPLNode(Node):
    """Executes a validated SPL query through the full SPL engine pipeline.

    Pipeline: parse → analyze → optimize → execute (parallel CTE dispatch)

    USING MODEL auto is resolved per-PROMPT before execution using the model
    router (task classifier + routing table + provider preference).

    shared store reads:  spl_query, spl_params, adapter, cache_enabled,
                         delivery_mode, provider
    shared store writes: execution_results, primary_result, error
    actions returned:    "sync" | "async" | "error"
    """

    def prep(self, shared):
        return {
            "spl_query":     shared["spl_query"],
            "params":        shared.get("spl_params", {}),
            "adapter":       shared.get("adapter", "claude_cli"),
            "cache":         shared.get("cache_enabled", False),
            "delivery_mode": shared.get("delivery_mode", "sync"),
            "provider":      shared.get("provider", ""),
        }

    def exec(self, prep_res):
        spl_query    = prep_res["spl_query"]
        params       = prep_res["params"]
        adapter_name = prep_res["adapter"]
        cache_enabled = prep_res["cache"]
        provider     = prep_res["provider"]

        ast      = parse(spl_query)
        analysis = Analyzer().analyze(ast)
        plans    = Optimizer().optimize(analysis)

        if not plans:
            _log.error("no PROMPT statements found in SPL query")
            return {"error": "No PROMPT statements found in SPL query"}

        _log.info(
            "execute start  adapter=%s  provider=%s  prompts=%d  cache=%s",
            adapter_name, provider or "(best-of-breed)", len(plans), cache_enabled,
        )

        executor = Executor(adapter_name=adapter_name, cache_enabled=cache_enabled)

        for s in ast.statements:
            if isinstance(s, CreateFunctionStatement):
                executor.functions.register(s)

        results = []
        for i, plan in enumerate(plans):
            stmt = _find_stmt(ast, plan.prompt_name)
            is_final = (i == len(plans) - 1)

            # ── Resolve USING MODEL auto ──────────────────────────────────────
            # Must update both stmt.model AND plan.model: the optimizer copies
            # stmt.model into plan.model at construction time, and the executor
            # reads plan.model (not stmt.model) when calling the adapter.
            if stmt is not None and (stmt.model or "").strip().lower() == "auto":
                system_role, instruction = _extract_texts(stmt)
                resolved = auto_route(
                    adapter=adapter_name,
                    system_role=system_role,
                    instruction=instruction,
                    provider=provider,
                    is_final_prompt=is_final,
                )
                stmt.model = resolved
                plan.model = resolved
                _log.info("[%s] USING MODEL auto → %s", plan.prompt_name, resolved)

            try:
                result = asyncio.run(executor.execute(plan, params=params, stmt=stmt))
            except Exception as exc:
                _log.error(
                    "[%s] LLM call failed  adapter=%s  model=%s  error=%s",
                    plan.prompt_name, adapter_name,
                    getattr(stmt, "model", "?") if stmt else "?",
                    exc,
                )
                executor.close()
                return {"error": f"[{plan.prompt_name}] {exc}"}

            cost_str = f"${result.cost_usd:.5f}" if result.cost_usd is not None else "—"
            _log.info(
                "[%s] done  model=%s  tokens=%d+%d=%d  latency=%.0fms  cost=%s",
                plan.prompt_name, result.model,
                result.input_tokens, result.output_tokens, result.total_tokens,
                result.latency_ms, cost_str,
            )
            results.append({
                "prompt_name":  plan.prompt_name,
                "content":      result.content,
                "model":        result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
                "latency_ms":   result.latency_ms,
                "cost_usd":     result.cost_usd,
            })

        executor.close()
        total_tokens  = sum(r["total_tokens"] for r in results)
        total_latency = sum(r["latency_ms"] for r in results)
        total_cost    = sum(r["cost_usd"] for r in results if r["cost_usd"] is not None)
        _log.info(
            "execute done  total_tokens=%d  total_latency=%.0fms  total_cost=$%.5f",
            total_tokens, total_latency, total_cost,
        )
        return {"results": results}

    def post(self, shared, prep_res, exec_res):
        if "error" in exec_res:
            shared["error"] = exec_res["error"]
            return "error"

        shared["execution_results"] = exec_res["results"]
        shared["primary_result"]    = exec_res["results"][-1]["content"]
        return prep_res["delivery_mode"]   # "sync" or "async"


# ── AST helpers ───────────────────────────────────────────────────────────────

def _find_stmt(ast, prompt_name: str) -> PromptStatement | None:
    """Locate a PromptStatement by name — searches top-level and CTE-nested."""
    # 1. Top-level statements
    for s in ast.statements:
        if isinstance(s, PromptStatement) and s.name == prompt_name:
            return s
    # 2. CTE-nested prompts (CTEs inside a top-level PromptStatement)
    for s in ast.statements:
        if isinstance(s, PromptStatement):
            for cte in s.ctes:
                if (
                    isinstance(cte, CTEClause)
                    and cte.nested_prompt is not None
                    and cte.nested_prompt.name == prompt_name
                ):
                    return cte.nested_prompt
    return None


def _extract_texts(stmt: PromptStatement) -> tuple[str, str]:
    """Return (system_role_text, generate_instruction) for task classification."""
    # system_role
    system_role = ""
    for item in (stmt.select_items or []):
        if isinstance(item.expression, SystemRoleCall):
            system_role = item.expression.description
            break

    # GENERATE instruction — last string argument of the generate clause
    instruction = ""
    gen = stmt.generate_clause
    if gen and gen.arguments:
        for arg in reversed(gen.arguments):
            for attr in ("value", "text", "content", "s"):
                v = getattr(arg, attr, None)
                if isinstance(v, str):
                    instruction = v
                    break
            if instruction:
                break

    return system_role, instruction
