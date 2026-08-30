"""
Stripe paywall — first run free, subsequent runs require payment.
Uses emergentintegrations StripeCheckout for Flow B (test key from env).
"""

import os
import logging
from datetime import datetime, timezone

from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CheckoutStatusResponse,
)

logger = logging.getLogger(__name__)

RUN_PRICE = 1.0  # $1.00 per run credit (test mode)


def get_stripe_checkout(webhook_url: str) -> StripeCheckout:
    return StripeCheckout(
        api_key=os.environ.get("STRIPE_API_KEY", "sk_test_emergent"),
        webhook_url=webhook_url,
    )


async def check_run_credits(db) -> dict:
    """
    Check if the user can start a run.
    First run is free; subsequent runs need a paid credit.
    Returns {can_run, free_used, paid_unused, total_runs}.
    """
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")

    if os.environ.get("DISABLE_PAYWALL", "").lower() in ("1", "true", "yes"):
        return {
            "can_run": True,
            "free_used": False,
            "paid_credits": 999,
            "total_runs": 0,
            "price": RUN_PRICE,
        }

    total_runs = await db.runs.count_documents({"outcome": {"$ne": "in_progress"}})
    paid_unused = await db.payment_transactions.count_documents({
        "payment_status": "paid",
        "credit_used": {"$ne": True},
    })

    free_used = total_runs > 0
    can_run = not free_used or paid_unused > 0

    return {
        "can_run": can_run,
        "free_used": free_used,
        "paid_credits": paid_unused,
        "total_runs": total_runs,
        "price": RUN_PRICE,
    }


async def consume_credit(db) -> bool:
    """
    Consume one run credit. Returns True if credit consumed, False if none available.
    First run is free (no credit needed). Subsequent runs consume a paid credit.

    Set DISABLE_PAYWALL=1 in the environment (local dev) to bypass this entirely.
    """
    if os.environ.get("DISABLE_PAYWALL", "").lower() in ("1", "true", "yes"):
        return True

    total_runs = await db.runs.count_documents({"outcome": {"$ne": "in_progress"}})

    # First run is free
    if total_runs == 0:
        return True

    # Try to consume a paid credit
    result = await db.payment_transactions.update_one(
        {"payment_status": "paid", "credit_used": {"$ne": True}},
        {"$set": {"credit_used": True, "used_at": datetime.now(timezone.utc).isoformat()}},
    )
    return result.modified_count > 0
