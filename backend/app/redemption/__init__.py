"""REAL Growth Points redemption at renewal (Phase 2, built and DISABLED; Phase 3 enables it, only through the gates in service.allowed()).

This package is the ONLY code allowed to put a points discount on an invoice. The shadow reward engine (app/rewards) never writes a
financial table; this package never edits an earning row. Keep it that way: tests scan for both.
"""
