"""ExecuteSPL Node: run the SPL engine against the configured LLM adapter."""
import sys
import asyncio
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")

from pocketflow import Node
from spl import parse
from spl.analyzer import Analyzer
from spl.optimizer import Optimizer
from spl.executor import Executor
from spl.ast_nodes import PromptStatement, CreateFunctionStatement


class ExecuteSPLNode(Node):
    """Executes a validated SPL query through the full SPL engine pipeline.

    Pipeline: parse → analyze → optimize → execute (with parallel CTE dispatch)

    shared store reads:  spl_query, spl_params, adapter, cache_enabled, delivery_mode
    shared store writes: execution_results, primary_result, error
    actions returned:    "sync" | "async" | "error"
    """

    def prep(self, shared):
        return {
            "spl_query": shared["spl_query"],
            "params": shared.get("spl_params", {}),
            "adapter": shared.get("adapter", "claude_cli"),
            "cache": shared.get("cache_enabled", False),
            "delivery_mode": shared.get("delivery_mode", "sync"),
        }

    def exec(self, prep_res):
        spl_query = prep_res["spl_query"]
        params = prep_res["params"]
        adapter_name = prep_res["adapter"]
        cache_enabled = prep_res["cache"]

        ast = parse(spl_query)
        analysis = Analyzer().analyze(ast)
        plans = Optimizer().optimize(analysis)

        if not plans:
            return {"error": "No PROMPT statements found in SPL query"}

        executor = Executor(adapter_name=adapter_name, cache_enabled=cache_enabled)

        # Register any CREATE FUNCTION definitions from the program
        for s in ast.statements:
            if isinstance(s, CreateFunctionStatement):
                executor.functions.register(s)

        results = []
        for plan in plans:
            stmt = None
            for s in ast.statements:
                if isinstance(s, PromptStatement) and s.name == plan.prompt_name:
                    stmt = s
                    break

            result = asyncio.run(executor.execute(plan, params=params, stmt=stmt))
            results.append({
                "prompt_name": plan.prompt_name,
                "content": result.content,
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
                "latency_ms": result.latency_ms,
                "cost_usd": result.cost_usd,
            })

        executor.close()
        return {"results": results}

    def post(self, shared, prep_res, exec_res):
        if "error" in exec_res:
            shared["error"] = exec_res["error"]
            return "error"

        shared["execution_results"] = exec_res["results"]
        # The last PROMPT result is the final composed output
        shared["primary_result"] = exec_res["results"][-1]["content"]

        return prep_res["delivery_mode"]  # "sync" or "async"
