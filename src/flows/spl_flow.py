"""SPL-Flow PocketFlow graph: text → SPL → validate → execute → deliver."""
from pocketflow import Flow
from src.nodes.text2spl import Text2SPLNode
from src.nodes.validate_spl import ValidateSPLNode
from src.nodes.execute_spl import ExecuteSPLNode
from src.nodes.deliver import SyncDeliverNode, AsyncDeliverNode


def build_spl_flow() -> Flow:
    """Build and return the full SPL-Flow PocketFlow graph.

    Flow graph:
        text2spl ──────────────────────► validate
            ▲                                │
            │ "retry" (parse error)          │ "execute" (valid)
            └────────────────────────────────┘
                                             ▼
                                          execute
                                         │       │
                                  "sync" │       │ "async"
                                         ▼       ▼
                                    sync_del  async_del
                                         │       │
                                         └── done ┘
    Note: execute "error" and validate "error" also route to sync_del (terminal).
    """
    text2spl = Text2SPLNode(max_retries=3)
    validate = ValidateSPLNode()
    execute = ExecuteSPLNode()
    sync_deliver = SyncDeliverNode()
    async_deliver = AsyncDeliverNode()

    # text2spl → validate (always)
    text2spl >> validate

    # validate → execute (success) or retry text2spl or terminal error
    validate - "execute" >> execute
    validate - "retry" >> text2spl
    validate - "error" >> sync_deliver

    # execute → sync or async delivery
    execute - "sync" >> sync_deliver
    execute - "async" >> async_deliver
    execute - "error" >> sync_deliver

    return Flow(start=text2spl)


def build_generate_only_flow() -> Flow:
    """Build a flow that stops after validation (no execution).

    Used for the "Generate SPL" step in the Streamlit UI so users
    can review and edit the SPL before committing to execution.
    """
    text2spl = Text2SPLNode(max_retries=3)
    validate = ValidateSPLNode()

    text2spl >> validate
    validate - "retry" >> text2spl
    # "execute" and "error" actions have no edge → flow terminates

    return Flow(start=text2spl)


def run_spl_flow(
    user_input: str,
    context_text: str = "",
    adapter: str = "claude_cli",
    delivery_mode: str = "sync",
    notify_email: str = "",
    spl_params: dict = None,
    cache_enabled: bool = False,
) -> dict:
    """Run the complete SPL-Flow pipeline (generate → validate → execute → deliver).

    Returns the shared store with all results populated.
    """
    flow = build_spl_flow()

    shared = {
        # Input
        "user_input": user_input,
        "context_text": context_text,
        "adapter": adapter,
        "delivery_mode": delivery_mode,
        "notify_email": notify_email,
        "spl_params": spl_params or {},
        "cache_enabled": cache_enabled,
        # Pipeline state (populated by nodes)
        "spl_query": "",
        "spl_ast": None,
        "spl_warnings": [],
        "last_parse_error": "",
        "retry_count": 0,
        "execution_results": [],
        "primary_result": "",
        "output_file": "",
        "email_sent": False,
        "delivered": False,
        "error": "",
    }

    flow.run(shared)
    return shared


def generate_spl_only(
    user_input: str,
    context_text: str = "",
) -> dict:
    """Run only the Text2SPL + Validate pipeline (no LLM execution).

    Used for the preview step — user reviews and optionally edits the
    generated SPL before triggering execution.

    Returns the shared store with spl_query populated.
    """
    flow = build_generate_only_flow()

    shared = {
        "user_input": user_input,
        "context_text": context_text,
        "spl_query": "",
        "spl_ast": None,
        "spl_warnings": [],
        "last_parse_error": "",
        "retry_count": 0,
        "error": "",
    }

    flow.run(shared)
    return shared
