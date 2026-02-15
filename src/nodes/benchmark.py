"""BenchmarkNode: run one SPL script against N models in parallel.

Implements the BENCHMARK keyword at the SPL-Flow pre-processor layer —
no SPL engine parser changes required.  Each entry in USING MODELS becomes
an independent execution with a patched copy of the script; all N copies
run concurrently via asyncio.gather.

Public helpers
--------------
parse_benchmark_block(text)  → dict   parse a BENCHMARK...CALL block
load_benchmark_spl(parsed)   → str    resolve SPL from inline or CALL file
patch_model(spl, model_id)   → str    replace every USING MODEL clause
"""
import sys
import re
import asyncio
import hashlib
from datetime import datetime, timezone

sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

from pocketflow import Node
from src.utils.logging_config import get_logger

_log = get_logger("nodes.benchmark")


# ── BENCHMARK block parser ────────────────────────────────────────────────────

def parse_benchmark_block(text: str) -> dict:
    """Parse a BENCHMARK block into its components.

    Accepted syntax::

        BENCHMARK <name>
        USING MODELS ['model1', 'model2', auto]
        [USING ADAPTER <adapter>]
        CALL <file.spl> [(<key=val>, ...)]
            OR
        <inline SPL content>

    Returns
    -------
    dict with keys:
        name        : str
        models      : list[str]   e.g. ["anthropic/claude-opus-4-6", "auto"]
        adapter     : str         e.g. "openrouter" (overrides shared if set)
        call_file   : str | None  e.g. "summarize.spl"
        call_args   : dict        e.g. {"document": "some value"}
        inline_spl  : str | None  inline SPL if no CALL
    """
    lines = text.strip().splitlines()
    result: dict = {
        "name":       "benchmark",
        "models":     ["auto"],
        "adapter":    "",
        "call_file":  None,
        "call_args":  {},
        "inline_spl": None,
    }

    i = 0
    # Line 0: BENCHMARK <name>
    if i < len(lines):
        m = re.match(r"BENCHMARK\s+(\w+)", lines[i], re.IGNORECASE)
        if m:
            result["name"] = m.group(1)
            i += 1

    spl_start = i
    while i < len(lines):
        line = lines[i].strip()

        # USING MODELS ['m1', 'm2', auto]
        m = re.match(r"USING\s+MODELS\s*\[([^\]]*)\]", line, re.IGNORECASE)
        if m:
            models = []
            for token in m.group(1).split(","):
                t = token.strip().strip("'\"")
                if t:
                    models.append(t)
            result["models"] = models
            spl_start = i + 1
            i += 1
            continue

        # USING ADAPTER <name>
        m = re.match(r"USING\s+ADAPTER\s+(\S+)", line, re.IGNORECASE)
        if m:
            result["adapter"] = m.group(1).strip("'\"")
            spl_start = i + 1
            i += 1
            continue

        # CALL <file.spl> [(key=val, ...)]
        m = re.match(r"CALL\s+(\S+\.spl)\s*(?:\(([^)]*)\))?", line, re.IGNORECASE)
        if m:
            result["call_file"] = m.group(1)
            args: dict = {}
            for part in (m.group(2) or "").split(","):
                part = part.strip()
                if "=" in part:
                    k, _, v = part.partition("=")
                    args[k.strip()] = v.strip().strip("'\"")
            result["call_args"] = args
            spl_start = i + 1
            i += 1
            break  # CALL is the last directive; rest is not inline SPL

        # Anything that doesn't start with a directive keyword → start of inline SPL
        if line and not re.match(r"(USING|CALL)\s+", line, re.IGNORECASE):
            break

        i += 1

    # Remaining lines form the inline SPL (only when no CALL)
    if result["call_file"] is None:
        inline = "\n".join(lines[spl_start:]).strip()
        if inline:
            result["inline_spl"] = inline

    return result


def load_benchmark_spl(parsed: dict, base_dir: str = ".") -> str:
    """Return the SPL content described by a parsed BENCHMARK block.

    If ``CALL file.spl(args)`` was specified, loads the file and substitutes
    ``context.key`` placeholders with the provided arg values.
    Otherwise returns ``inline_spl`` directly.
    """
    if parsed.get("inline_spl"):
        return parsed["inline_spl"]

    if parsed.get("call_file"):
        import os
        path = os.path.join(base_dir, parsed["call_file"])
        with open(path, encoding="utf-8") as f:
            content = f.read()
        for k, v in parsed.get("call_args", {}).items():
            content = content.replace(f"context.{k}", repr(v))
        return content

    return ""


# ── Model patching ────────────────────────────────────────────────────────────

# Matches USING MODEL followed by a quoted string OR the bare word "auto"
_USING_MODEL_RE = re.compile(
    r"(USING\s+MODEL\s+)(?:'[^']*'|\"[^\"]*\"|auto\b)",
    re.IGNORECASE,
)


def patch_model(spl: str, model_id: str) -> str:
    """Replace every ``USING MODEL <x>`` clause in *spl* with *model_id*.

    ``model_id == "auto"``  →  ``USING MODEL auto``   (unquoted; late-bound)
    any other value         →  ``USING MODEL 'model_id'``  (quoted; early-bound)
    """
    if model_id.lower() == "auto":
        replacement = r"\g<1>auto"
    else:
        replacement = rf"\g<1>'{model_id}'"
    return _USING_MODEL_RE.sub(replacement, spl)


# ── Async single-model executor ───────────────────────────────────────────────

async def _run_one(
    model_id: str,
    resolved_from: str,
    patched_spl: str,
    adapter: str,
    provider: str,
    params: dict,
    cache_enabled: bool,
) -> dict:
    """Execute *patched_spl* against one model and return a run dict."""
    from spl import parse as spl_parse
    from spl.analyzer import Analyzer
    from spl.optimizer import Optimizer
    from spl.executor import Executor
    from spl.ast_nodes import CreateFunctionStatement
    from src.nodes.execute_spl import _find_stmt, _extract_texts
    from src.utils.model_router import auto_route

    try:
        ast      = spl_parse(patched_spl)
        analysis = Analyzer().analyze(ast)
        plans    = Optimizer().optimize(analysis)

        if not plans:
            return _error_run(
                model_id, resolved_from, patched_spl,
                "No PROMPT statements found in SPL query",
            )

        executor = Executor(adapter_name=adapter, cache_enabled=cache_enabled)

        for s in ast.statements:
            if isinstance(s, CreateFunctionStatement):
                executor.functions.register(s)

        prompt_results = []
        for i, plan in enumerate(plans):
            stmt     = _find_stmt(ast, plan.prompt_name)
            is_final = (i == len(plans) - 1)

            # Late binding: resolve "auto" at routing-time, just before LLM call
            if stmt is not None and (stmt.model or "").strip().lower() == "auto":
                system_role, instruction = _extract_texts(stmt)
                stmt.model = auto_route(
                    adapter=adapter,
                    system_role=system_role,
                    instruction=instruction,
                    provider=provider,
                    is_final_prompt=is_final,
                )

            r = await executor.execute(plan, params=params, stmt=stmt)
            prompt_results.append({
                "prompt_name":  plan.prompt_name,
                "model_id":     r.model,
                "response":     r.content,
                "input_tokens":  r.input_tokens,
                "output_tokens": r.output_tokens,
                "total_tokens":  r.total_tokens,
                "latency_ms":    r.latency_ms,
                "cost_usd":      r.cost_usd,
            })

        executor.close()

        final = prompt_results[-1]
        run: dict = {
            "model_id":      model_id,
            "resolved_from": resolved_from,
            "input_spl":     patched_spl,
            "response":      final["response"],
            "input_tokens":  sum(p["input_tokens"]  for p in prompt_results),
            "output_tokens": sum(p["output_tokens"] for p in prompt_results),
            "total_tokens":  sum(p["total_tokens"]  for p in prompt_results),
            "latency_ms":    sum(p["latency_ms"]    for p in prompt_results),
            "cost_usd": (
                sum(p["cost_usd"] for p in prompt_results
                    if p["cost_usd"] is not None)
                if any(p["cost_usd"] is not None for p in prompt_results)
                else None
            ),
            "prompt_results": prompt_results,
            "error": "",
        }

        # Record the concrete model the router chose (for auto runs)
        if resolved_from == "auto" and prompt_results:
            run["resolved_model"] = final["model_id"]

        return run

    except Exception as exc:
        return _error_run(model_id, resolved_from, patched_spl, str(exc))


def _error_run(
    model_id: str,
    resolved_from: str,
    patched_spl: str,
    error: str,
) -> dict:
    """Return a run dict representing a failed execution."""
    return {
        "model_id":       model_id,
        "resolved_from":  resolved_from,
        "input_spl":      patched_spl,
        "response":       "",
        "input_tokens":   0,
        "output_tokens":  0,
        "total_tokens":   0,
        "latency_ms":     0.0,
        "cost_usd":       None,
        "prompt_results": [],
        "error":          error,
    }


# ── BenchmarkNode ─────────────────────────────────────────────────────────────

class BenchmarkNode(Node):
    """Run the same SPL script against N models in parallel, return JSON results.

    All N model executions run concurrently via ``asyncio.gather`` — wall-clock
    time is approximately equal to the slowest single model, not N × one model.

    shared store reads:  spl_query, benchmark_models, benchmark_name,
                         adapter, provider, spl_params, cache_enabled
    shared store writes: benchmark_result
    actions returned:    "done" | "error"
    """

    def prep(self, shared):
        return {
            "spl_query":      shared["spl_query"],
            "models":         shared.get("benchmark_models", ["auto"]),
            "benchmark_name": shared.get("benchmark_name", ""),
            "adapter":        shared.get("adapter", "claude_cli"),
            "provider":       shared.get("provider", ""),
            "params":         shared.get("spl_params", {}),
            "cache":          shared.get("cache_enabled", False),
        }

    def exec(self, prep_res):
        spl     = prep_res["spl_query"]
        models  = prep_res["models"]
        adapter = prep_res["adapter"]
        provider = prep_res["provider"]
        params  = prep_res["params"]
        cache   = prep_res["cache"]

        _log.info(
            "benchmark start  name=%s  models=%d  adapter=%s  provider=%s",
            prep_res["benchmark_name"], len(models), adapter,
            provider or "(best-of-breed)",
        )
        _log.info("benchmark models: %s", ", ".join(models))

        patches = [
            (
                model_id,
                "auto" if model_id.lower() == "auto" else "explicit",
                patch_model(spl, model_id),
            )
            for model_id in models
        ]

        t_start = __import__("time").monotonic()

        async def run_all():
            tasks = [
                _run_one(mid, rfrom, pspl, adapter, provider, params, cache)
                for mid, rfrom, pspl in patches
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

        raw = asyncio.run(run_all())

        wall_ms = (__import__("time").monotonic() - t_start) * 1000

        runs = []
        for (model_id, resolved_from, patched_spl), result in zip(patches, raw):
            if isinstance(result, Exception):
                _log.error("[%s] run failed: %s", model_id, result)
                runs.append(_error_run(model_id, resolved_from, patched_spl, str(result)))
            else:
                run = result
                if run.get("error"):
                    _log.error("[%s] run error: %s", model_id, run["error"])
                else:
                    cost_str = (f"${run['cost_usd']:.5f}"
                                if run.get("cost_usd") is not None else "—")
                    _log.info(
                        "[%s] ok  resolved=%s  tokens=%d  latency=%.0fms  cost=%s",
                        model_id,
                        run.get("resolved_model") or resolved_from,
                        run.get("total_tokens", 0),
                        run.get("latency_ms", 0),
                        cost_str,
                    )
                runs.append(run)

        _log.info(
            "benchmark done  runs=%d  wall_clock=%.0fms",
            len(runs), wall_ms,
        )
        return {"runs": runs}

    def post(self, shared, prep_res, exec_res):
        if not exec_res["runs"]:
            shared["error"] = "Benchmark produced no results"
            return "error"

        spl_hash = hashlib.sha256(
            prep_res["spl_query"].strip().encode()
        ).hexdigest()[:32]

        shared["benchmark_result"] = {
            "benchmark_name": prep_res["benchmark_name"],
            "adapter":        prep_res["adapter"],
            "timestamp":      datetime.now(timezone.utc).isoformat(),
            "spl_hash":       spl_hash,
            "params":         prep_res["params"],
            "winner":         None,
            "runs":           exec_res["runs"],
        }
        return "done"
