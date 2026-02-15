"""Deliver Node: sync and async result delivery."""
import time
from pocketflow import Node


class SyncDeliverNode(Node):
    """Sync delivery — result is already in shared store, just mark as delivered.

    Also acts as the terminal error node (error message stays in shared["error"]).

    shared store reads:  primary_result
    shared store writes: delivered, delivery_time
    actions returned:    "done"
    """

    def prep(self, shared):
        return shared.get("primary_result", "")

    def exec(self, result):
        return result  # pass through

    def post(self, shared, prep_res, exec_res):
        shared["delivered"] = True
        shared["delivery_time"] = time.time()
        return "done"


class AsyncDeliverNode(Node):
    """Async delivery — saves result to file and optionally notifies by email.

    For MVP: saves to /tmp/ and sets a download path.
    Email: placeholder (configure SMTP in v0.2).

    shared store reads:  primary_result, notify_email, output_format
    shared store writes: output_file, email_sent, delivered
    actions returned:    "done"
    """

    def prep(self, shared):
        return {
            "result": shared.get("primary_result", ""),
            "email": shared.get("notify_email", ""),
            "output_format": shared.get("output_format", "markdown"),
        }

    def exec(self, prep_res):
        result = prep_res["result"]

        # Save to file
        timestamp = int(time.time())
        filename = f"/tmp/spl_flow_result_{timestamp}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(result)

        # Email notification placeholder
        email = prep_res["email"]
        email_sent = False
        if email:
            # TODO: integrate SMTP in v0.2
            # send_email(to=email, subject="SPL-Flow result ready", body=result)
            email_sent = False  # Set True once SMTP is configured

        return {"filename": filename, "email_sent": email_sent, "email": email}

    def post(self, shared, prep_res, exec_res):
        shared["output_file"] = exec_res["filename"]
        shared["email_sent"] = exec_res["email_sent"]
        shared["delivered"] = True
        return "done"
