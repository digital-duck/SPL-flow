"""Benchmark flow: single-node PocketFlow graph for BENCHMARK execution."""
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL-Flow")

from pocketflow import Flow
from src.nodes.benchmark import BenchmarkNode


def build_benchmark_flow() -> Flow:
    """Build the benchmark flow — a single BenchmarkNode, terminal on 'done'."""
    node = BenchmarkNode()
    # No outgoing edges — flow terminates after BenchmarkNode returns "done"
    return Flow(start=node)


def run_benchmark_flow(
    spl_query: str,
    *,
    benchmark_name: str = "",
    models: list | None = None,
    adapter: str = "claude_cli",
    provider: str = "",
    spl_params: dict | None = None,
    cache_enabled: bool = False,
) -> dict:
    """Run *spl_query* against each model in *models* in parallel.

    Parameters
    ----------
    spl_query      : valid SPL script (no BENCHMARK wrapper needed)
    benchmark_name : human-readable label for the result JSON
    models         : list of model IDs to benchmark against;
                     ``"auto"`` is a valid entry (resolved at routing-time)
    adapter        : LLM adapter — "claude_cli" | "openrouter" | "ollama"
    provider       : optional org provider preference for auto routing
    spl_params     : extra context params injected into the SPL
    cache_enabled  : enable SQLite result cache

    Returns
    -------
    The full shared store dict.  ``shared["benchmark_result"]`` contains
    the structured BenchmarkResult with all run metrics.
    """
    flow = build_benchmark_flow()

    shared = {
        # Input
        "spl_query":        spl_query,
        "benchmark_name":   benchmark_name,
        "benchmark_models": models or ["auto"],
        "adapter":          adapter,
        "provider":         provider,
        "spl_params":       spl_params or {},
        "cache_enabled":    cache_enabled,
        # Output (populated by BenchmarkNode)
        "benchmark_result": {},
        "error":            "",
    }

    flow.run(shared)
    return shared
