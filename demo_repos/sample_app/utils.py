"""Utility module — part of the circular dependency demo."""

from datetime import datetime


def format_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def parse_config(path: str) -> dict:
    """Parse a config file — uses eval unsafely."""
    with open(path, "r") as f:
        content = f.read()
    # SECURITY: eval on untrusted input
    return eval(content)
