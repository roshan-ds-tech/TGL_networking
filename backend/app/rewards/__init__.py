"""Growth Points: Phase 1, SHADOW MODE ONLY.

Points are calculated and recorded in an append-only shadow ledger so management can see what the economy WOULD do.
They have no monetary effect: nothing here changes an invoice, a payment, a price or a subscription, and there is no
redemption. See rules.py (the one place the numbers live), engine.py (the one reward engine) and firewall.py.
"""
from . import ledger as _ledger  # noqa: F401  (registers the append-only guard on the ledger)
from . import firewall  # noqa: F401  (registers the financial-write guard)
