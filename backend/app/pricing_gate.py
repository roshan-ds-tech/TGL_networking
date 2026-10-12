"""The subscription-pricing safety gate.

Growth Points are not active, so nothing may reduce an invoice today. When that
changes, any code that lets points (or any other credit) lower what a member pays
MUST pass through `require_pricing_confirmed()` first. It is the ONLY place allowed to
read `settings.subscription_pricing_confirmed`; test_phase0.py scans the codebase and
fails if another module reads the setting, so the gate cannot be bypassed by reading
the flag (or ignoring it) somewhere else.

Fail-closed by design:
  * the default is "not confirmed";
  * an unparseable value stops the app starting (pydantic bool) rather than reading as true;
  * a live (non-zero) invoice discount is independently impossible while the database
    CHECK `ck_invoice_no_discount_phase0` exists, so lifting this gate alone is not
    enough to discount anything - that constraint must be replaced by a reviewed migration.

Nothing here awards, calculates or applies Growth Points.
"""
from __future__ import annotations

from .config import settings


class PricingNotConfirmed(RuntimeError):
    """Raised when a price-affecting feature runs before management confirmed the plan prices."""


def pricing_confirmed() -> bool:
    return settings.subscription_pricing_confirmed is True


def require_pricing_confirmed(feature: str) -> None:
    """Call at the top of any code path that could change what an invoice charges."""
    if not pricing_confirmed():
        raise PricingNotConfirmed(
            f"{feature} is disabled: SUBSCRIPTION_PRICING_CONFIRMED is false (management has not "
            "confirmed the plan prices and terms: Connect 3, Growth 6 and Elite 12 months)."
        )
