"""Transactional email via Resend's HTTP API.

Deliberately not SMTP: Resend's free tier needs only a verified sending
domain (DNS records) and an API key — no mailbox/hosting purchase, no SMTP
credentials to rotate. See docs/P0_IMPLEMENTATION.md for the DNS setup.
"""
from __future__ import annotations

import logging

import httpx

from . import http_client
from .config import settings

logger = logging.getLogger("tgl")



def _mask(email: str) -> str:
    """'as***@example.com' — enough to trace a delivery problem in logs
    without writing full addresses into them."""
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}"


async def deliver(to_email: str, subject: str, html: str, text: str, idempotency_key: str) -> str:
    """Send one email via Resend. Never raises. Returns:
      "sent"    — accepted by Resend
      "skipped" — no RESEND_API_KEY configured (local dev / tests)
      "retry"   — transient problem (network, 429, 5xx): try again later
      "failed"  — Resend refused it permanently (4xx): don't retry

    The Idempotency-Key makes a retried attempt harmless: Resend sends a
    given key at most once, so an outbox row re-claimed after a crash can't
    produce a duplicate email."""
    if not settings.resend_api_key:
        logger.warning("RESEND_API_KEY not set; skipping email (%s) to %s", subject, _mask(to_email))
        return "skipped"
    try:
        response = await http_client.request(
            "POST",
            settings.resend_api_url,
            headers={"Authorization": f"Bearer {settings.resend_api_key}", "Idempotency-Key": idempotency_key},
            json={"from": settings.email_from, "to": [to_email], "subject": subject, "html": html, "text": text},
        )
    except httpx.HTTPError:
        logger.warning("Email (%s) to %s: network error, will retry", subject, _mask(to_email))
        return "retry"
    if response.status_code < 300:
        return "sent"
    if response.status_code == 429 or response.status_code >= 500:
        logger.warning("Email (%s) to %s: HTTP %s, will retry", subject, _mask(to_email), response.status_code)
        return "retry"
    logger.error("Resend rejected email (%s) to %s: HTTP %s", subject, _mask(to_email), response.status_code)
    return "failed"


def verification_email(code: str) -> tuple[str, str, str]:
    return (
        "Your TGL verification code",
        _code_html("Verify your email", "Enter this code to activate your TGL account:", code, 10),
        f"Your TGL verification code is {code}. It expires in 10 minutes.",
    )


def login_otp_email(code: str) -> tuple[str, str, str]:
    return (
        "Your TGL sign-in code",
        _code_html("Sign in to TGL", "Enter this code to sign in:", code, 10),
        f"Your TGL sign-in code is {code}. It expires in 10 minutes.",
    )


def password_reset_email(reset_url: str) -> tuple[str, str, str]:
    html = (
        '<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;'
        'max-width:480px;margin:0 auto;padding:32px 24px;">'
        '<h2 style="margin:0 0 12px;color:#2B1740;">Reset your password</h2>'
        '<p style="margin:0 0 20px;color:#4a4a4a;font-size:14px;">'
        "Click the link below to choose a new password:</p>"
        f'<a href="{reset_url}" style="display:inline-block;padding:14px 24px;'
        'border-radius:999px;background:#C08D2E;color:#22103A;font-weight:700;'
        'text-decoration:none;">Reset password</a>'
        '<p style="margin:20px 0 0;color:#8a8a8a;font-size:12.5px;">'
        "This link expires in 30 minutes. If you did not request this, "
        "you can ignore this email.</p></div>"
    )
    text = f"Reset your TGL password: {reset_url} (expires in 30 minutes)"
    return "Reset your TGL password", html, text


def _code_html(heading: str, lede: str, code: str, expires_minutes: int) -> str:
    return (
        '<div style="font-family:-apple-system,Helvetica,Arial,sans-serif;'
        'max-width:480px;margin:0 auto;padding:32px 24px;">'
        f'<h2 style="margin:0 0 12px;color:#2B1740;">{heading}</h2>'
        f'<p style="margin:0 0 20px;color:#4a4a4a;font-size:14px;">{lede}</p>'
        '<div style="font-size:32px;font-weight:800;letter-spacing:8px;'
        f'color:#C08D2E;padding:16px 0;">{code}</div>'
        '<p style="margin:20px 0 0;color:#8a8a8a;font-size:12.5px;">'
        f"This code expires in {expires_minutes} minutes. If you did not request this, "
        "you can ignore this email.</p></div>"
    )
