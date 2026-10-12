"""The financial firewall: Growth Points in shadow mode can not touch money.

Four independent layers, so that no single mistake (or a manual call) can turn a shadow point into a real discount:

  1. While the reward engine runs, ANY statement that would INSERT, UPDATE or DELETE `invoices`, `payments`,
     `subscriptions` or `plans` is refused at the database-driver level (ORM, bulk and raw SQL alike).
  2. `redeem()` always raises, and there is no other redemption code. `GROWTH_POINTS_REDEMPTION_ENABLED=true` stops the
     application starting (config.py).
  3. The shadow ledger cannot hold a non-shadow row or a REDEMPTION row (CHECK constraints), and cannot be edited.
  4. The invoice CHECK `ck_invoice_no_discount_phase0` still holds every discount at zero.

This module is the ONLY reader of the Growth Points feature flags.
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.engine import Engine

from ..config import settings

_active: ContextVar[bool] = ContextVar("growth_points_engine_active", default=False)
_WRITE = re.compile(r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP)\b", re.I)
_FINANCIAL = re.compile(r"\b(invoices|payments|subscriptions|plans)\b", re.I)


class FinancialFirewallError(RuntimeError):
    """The reward engine tried to write to a financial table."""


class RedemptionDisabled(RuntimeError):
    """Growth Points cannot be redeemed: shadow mode is the only mode that exists."""


def shadow_enabled() -> bool:
    return settings.growth_points_shadow_mode is True


def member_preview_enabled() -> bool:
    return settings.growth_points_shadow_mode is True and settings.growth_points_member_preview is True


def redemption_enabled() -> bool:
    """The hard flag for REAL redemption. False by default; the application refuses to boot with it true unless every external approval is
    recorded (config.py), and app/redemption/service.allowed() then still requires Gate A, the rollout stage and an open kill switch."""
    return settings.growth_points_redemption_enabled is True


@contextmanager
def guard():
    """Run reward-engine work inside this: a write to any financial table raises FinancialFirewallError."""
    token = _active.set(True)
    try:
        yield
    finally:
        _active.reset(token)


def active() -> bool:
    return _active.get()


@event.listens_for(Engine, "before_cursor_execute")
def _refuse_financial_writes(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001 - SQLAlchemy hook signature
    if _active.get() and _WRITE.match(statement) and _FINANCIAL.search(statement):
        raise FinancialFirewallError(f"Growth Points (shadow mode) may not write to a financial table: {statement[:80]!r}")


def redeem(*_args, **_kwargs):
    """There is no redemption in Phase 1. Every call refuses, whatever the flags say."""
    raise RedemptionDisabled("Growth Points are in shadow mode: they cannot be redeemed, and nothing is applied to any invoice.")
