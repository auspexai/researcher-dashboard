"""Sanitized error detail for HTTP responses (CodeQL py/stack-trace-exposure).

The dashboard is normally bound to localhost and its "external user" is the
researcher running it, so leaking an exception string is a mild problem here —
but it stops being mild the moment someone puts it behind a tunnel, and the
diagnostics were flowing to the response verbatim.

The tension worth naming: stripping detail entirely makes a debugging tool
harder to debug, which is a real cost, not a hypothetical one. So this keeps a
useful one-line summary in the response and puts the FULL exception, with
traceback, in the server log where it belongs.

Use `safe_detail(e)` wherever an exception would otherwise be interpolated into
a response body.
"""

from __future__ import annotations

import logging

# Long enough to identify the failure, short enough that a paths-and-internals
# dump cannot ride along.
MAX_DETAIL_CHARS = 200


def safe_detail(exc: BaseException, *, logger: logging.Logger, context: str) -> str:
    """Log `exc` in full (with traceback) and return a short, response-safe summary.

    The summary is `TypeName: message`, truncated. Nothing multi-line survives:
    a traceback interpolated into JSON is exactly the finding this closes."""
    logger.exception("%s", context)
    message = " ".join(str(exc).split())
    if len(message) > MAX_DETAIL_CHARS:
        message = message[: MAX_DETAIL_CHARS - 1].rstrip() + "…"
    name = type(exc).__name__
    return f"{name}: {message}" if message else name
