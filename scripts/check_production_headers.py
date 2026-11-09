#!/usr/bin/env python3
"""Verify production browser security headers on the public hostname."""

from __future__ import annotations

import argparse
import ssl
import sys
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, Request, build_opener

REQUIRED_HSTS_MAX_AGE = 31536000
REQUIRED_CSP = (
    "default-src 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "script-src 'self'",
)


def _fetch_headers(url: str) -> tuple[int, Message]:
    context = ssl.create_default_context()
    opener = build_opener(HTTPSHandler(context=context))
    request = Request(
        url,
        method="GET",
        headers={"User-Agent": "agentgate-security-header-check/1.0"},
    )
    with opener.open(request, timeout=15) as response:
        return response.status, response.headers


def _check_hsts(
    value: str | None,
    expect_subdomains: bool,
    expect_preload: bool,
) -> list[str]:
    if not value:
        return ["Strict-Transport-Security header is missing"]

    directives: dict[str, str] = {}
    for part in value.split(";"):
        name, separator, raw_value = part.strip().partition("=")
        if name:
            directives[name.lower()] = raw_value.strip().strip('"') if separator else ""

    errors: list[str] = []
    try:
        max_age = int(directives.get("max-age", ""))
    except ValueError:
        errors.append("Strict-Transport-Security max-age is missing or invalid")
    else:
        if max_age < REQUIRED_HSTS_MAX_AGE:
            errors.append(
                f"Strict-Transport-Security max-age is {max_age}, "
                f"expected at least {REQUIRED_HSTS_MAX_AGE}"
            )

    has_subdomains = "includesubdomains" in directives
    has_preload = "preload" in directives
    if has_subdomains != expect_subdomains:
        errors.append(
            "Strict-Transport-Security includeSubDomains is "
            f"{'present' if has_subdomains else 'absent'}"
        )
    if has_preload != expect_preload:
        errors.append(
            "Strict-Transport-Security preload is "
            f"{'present' if has_preload else 'absent'}"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hostname", help="Public hostname, for example app.example.com")
    parser.add_argument(
        "--expect-hsts-subdomains",
        action="store_true",
        help="Require includeSubDomains after every subdomain is confirmed HTTPS",
    )
    parser.add_argument(
        "--expect-hsts-preload",
        action="store_true",
        help="Require preload after the domain is confirmed preload-ready",
    )
    args = parser.parse_args()

    url = f"https://{args.hostname.strip().rstrip('/')}/healthz"
    try:
        status, headers = _fetch_headers(url)
    except HTTPError as exc:
        print(f"FAIL {url}: HTTP {exc.code}", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, ssl.SSLError) as exc:
        print(f"FAIL {url}: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    if status != 200:
        errors.append(f"HTTP status is {status}, expected 200")

    hsts = headers.get("Strict-Transport-Security")
    errors.extend(
        _check_hsts(hsts, args.expect_hsts_subdomains, args.expect_hsts_preload)
    )

    csp = headers.get("Content-Security-Policy")
    if not csp:
        errors.append("Content-Security-Policy header is missing")
    else:
        for directive in REQUIRED_CSP:
            if directive not in csp:
                errors.append(f"Content-Security-Policy is missing {directive!r}")
        if "unsafe-inline" in csp:
            errors.append("Content-Security-Policy allows unsafe-inline")

    expected_headers = {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }
    for name, expected in expected_headers.items():
        actual = headers.get(name)
        if actual != expected:
            errors.append(f"{name} is {actual!r}, expected {expected!r}")

    if errors:
        print(f"FAIL {url} (HTTP {status})", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"OK {url} (HTTP {status})")
    print(f"  Strict-Transport-Security: {hsts}")
    print(f"  Content-Security-Policy: {csp}")
    for name, expected in expected_headers.items():
        print(f"  {name}: {expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
