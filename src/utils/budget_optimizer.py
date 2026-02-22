"""SPL Budget Optimizer - Post-processes generated SPL to ensure consistent token budgets.

Fixes the common issue where LLMs generate SPL with inconsistent budget math,
such as LIMIT clauses + OUTPUT BUDGET exceeding the total WITH BUDGET allocation.
"""

import re
import logging
from typing import List, Tuple, Optional

_log = logging.getLogger(__name__)


class SPLBudgetOptimizer:
    """Post-processor that analyzes and fixes token budget allocation in SPL queries."""

    # Regex patterns for extracting budget information
    MAIN_BUDGET_RE = re.compile(r'WITH\s+BUDGET\s+(\d+)\s+tokens', re.IGNORECASE)
    OUTPUT_BUDGET_RE = re.compile(r'WITH\s+OUTPUT\s+BUDGET\s+(\d+)\s+tokens', re.IGNORECASE)
    LIMIT_RE = re.compile(r'LIMIT\s+(\d+)\s+tokens', re.IGNORECASE)

    def __init__(self, safety_margin: float = 0.90):
        """
        Args:
            safety_margin: Use only this fraction of total budget (e.g., 0.90 = 90%)
        """
        self.safety_margin = safety_margin

    def optimize(self, spl: str) -> str:
        """
        Analyze and optimize token budget allocation in SPL.

        Args:
            spl: Raw SPL string from LLM

        Returns:
            SPL with corrected budget allocations
        """
        try:
            return self._optimize_internal(spl)
        except Exception as e:
            _log.warning(f"Budget optimization failed: {e}. Returning original SPL.")
            return spl

    def _optimize_internal(self, spl: str) -> str:
        """Internal optimization logic with error handling."""
        # Extract budget information
        main_budget = self._extract_main_budget(spl)
        if not main_budget:
            _log.debug("No main budget found, skipping optimization")
            return spl

        limit_totals = self._extract_limit_totals(spl)
        output_budget = self._extract_output_budget(spl)

        if not output_budget:
            _log.debug("No output budget found, skipping optimization")
            return spl

        # Check if budget is already consistent
        total_used = limit_totals + output_budget
        if total_used <= main_budget:
            _log.debug(f"Budget already consistent: {total_used} ≤ {main_budget}")
            return spl

        _log.info(f"Budget inconsistent: {total_used} > {main_budget}. Optimizing...")

        # Apply optimization
        return self._redistribute_budget(spl, main_budget, limit_totals, output_budget)

    def _extract_main_budget(self, spl: str) -> Optional[int]:
        """Extract the main WITH BUDGET value."""
        match = self.MAIN_BUDGET_RE.search(spl)
        return int(match.group(1)) if match else None

    def _extract_output_budget(self, spl: str) -> Optional[int]:
        """Extract the OUTPUT BUDGET value from the main GENERATE clause."""
        match = self.OUTPUT_BUDGET_RE.search(spl)
        return int(match.group(1)) if match else None

    def _extract_limit_totals(self, spl: str) -> int:
        """Extract and sum all LIMIT token values from SELECT clauses."""
        limit_matches = self.LIMIT_RE.findall(spl)
        return sum(int(limit) for limit in limit_matches)

    def _redistribute_budget(self, spl: str, main_budget: int,
                           limit_totals: int, output_budget: int) -> str:
        """
        Redistribute budget proportionally to fix over-allocation.

        Strategy:
        1. Apply safety margin to main budget (e.g., use 90% of available)
        2. Allocate 25% to output, 75% to context limits
        3. Distribute context budget proportionally across all LIMIT clauses
        """
        available_budget = int(main_budget * self.safety_margin)

        # Allocate budget: 75% for context, 25% for output
        new_output_budget = int(available_budget * 0.25)
        total_limit_budget = int(available_budget * 0.75)

        _log.info(f"Redistributing {main_budget} tokens: {total_limit_budget} context + {new_output_budget} output")

        # Update output budget
        spl = self.OUTPUT_BUDGET_RE.sub(
            f'WITH OUTPUT BUDGET {new_output_budget} tokens',
            spl
        )

        # Update LIMIT clauses proportionally
        if limit_totals > 0:
            spl = self._scale_limit_clauses(spl, limit_totals, total_limit_budget)

        return spl

    def _scale_limit_clauses(self, spl: str, current_total: int, target_total: int) -> str:
        """Scale all LIMIT clauses proportionally to fit target budget."""
        scale_factor = target_total / current_total

        def scale_limit(match):
            old_limit = int(match.group(1))
            new_limit = max(50, int(old_limit * scale_factor))  # Minimum 50 tokens
            _log.debug(f"Scaling LIMIT: {old_limit} → {new_limit} tokens")
            return f'LIMIT {new_limit} tokens'

        return self.LIMIT_RE.sub(scale_limit, spl)


# ── Convenience function ──────────────────────────────────────────────────────

def optimize_spl_budget(spl: str, safety_margin: float = 0.90) -> str:
    """
    Convenience function to optimize SPL budget allocation.

    Args:
        spl: Raw SPL string from LLM
        safety_margin: Fraction of total budget to use (default 90%)

    Returns:
        SPL with optimized budget allocation

    Example:
        >>> spl = '''
        ... PROMPT test WITH BUDGET 8000 tokens
        ... SELECT context.data LIMIT 3000 tokens
        ... GENERATE task() WITH OUTPUT BUDGET 6000 tokens;
        ... '''
        >>> optimized = optimize_spl_budget(spl)
        # Result: LIMIT ~5400, OUTPUT ~1200 to fit within 7200 (90% of 8000)
    """
    optimizer = SPLBudgetOptimizer(safety_margin)
    return optimizer.optimize(spl)


# ── Validation helper ─────────────────────────────────────────────────────────

def validate_spl_budget(spl: str) -> dict:
    """
    Analyze SPL budget allocation and return validation report.

    Returns:
        Dictionary with keys: main_budget, limit_total, output_budget,
        total_used, is_valid, utilization
    """
    optimizer = SPLBudgetOptimizer()

    main_budget = optimizer._extract_main_budget(spl)
    limit_totals = optimizer._extract_limit_totals(spl)
    output_budget = optimizer._extract_output_budget(spl)

    total_used = limit_totals + (output_budget or 0)
    is_valid = total_used <= (main_budget or 0)
    utilization = (total_used / main_budget) if main_budget else 0

    return {
        "main_budget": main_budget,
        "limit_total": limit_totals,
        "output_budget": output_budget,
        "total_used": total_used,
        "is_valid": is_valid,
        "utilization": utilization,
        "recommendation": "optimize" if not is_valid else "ok"
    }