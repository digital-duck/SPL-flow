"""ValidateSPL Node: parse and validate generated SPL, retry on error."""
import sys
sys.path.insert(0, "/home/papagame/projects/digital-duck/SPL")

from pocketflow import Node
from spl import parse
from spl.analyzer import Analyzer


class ValidateSPLNode(Node):
    """Parses and semantically validates the generated SPL.

    shared store reads:  spl_query, retry_count
    shared store writes: spl_ast, spl_warnings, last_parse_error, error
    actions returned:    "execute" (valid), "retry" (invalid, under limit), "error" (give up)
    """

    MAX_RETRIES = 3

    def prep(self, shared):
        return {
            "spl_query": shared.get("spl_query", ""),
            "retry_count": shared.get("retry_count", 0),
        }

    def exec(self, prep_res):
        try:
            ast = parse(prep_res["spl_query"])
            analysis = Analyzer().analyze(ast)
            return {
                "valid": True,
                "ast": ast,
                "warnings": [str(w) for w in analysis.warnings],
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def post(self, shared, prep_res, exec_res):
        if exec_res["valid"]:
            shared["spl_ast"] = exec_res["ast"]
            shared["spl_warnings"] = exec_res.get("warnings", [])
            shared["last_parse_error"] = ""
            return "execute"

        # Retry if under limit
        if prep_res["retry_count"] < self.MAX_RETRIES:
            shared["last_parse_error"] = exec_res["error"]
            return "retry"

        # Give up after max retries
        shared["error"] = (
            f"Failed to generate valid SPL after {self.MAX_RETRIES} attempts. "
            f"Last parse error: {exec_res['error']}"
        )
        return "error"
