"""Sanitized error detail for HTTP responses (CodeQL py/stack-trace-exposure).

The dashboard is normally bound to localhost and its "external user" is the
researcher running it, so leaking exception text is mild here — but it stops
being mild the moment someone puts it behind a tunnel, and the diagnostics were
flowing into response bodies verbatim.

**Why this returns a reference and not the exception text.** The first attempt
kept a truncated `TypeName: message` in the response. That is a real improvement
— the traceback goes to the log, the response is bounded to one line — but it
does NOT clear the finding, because exception-derived data still reaches the
client and that is exactly what the query tracks. Truncating tainted data leaves
it tainted.

So: the full exception, with traceback, goes to the log under a short random
reference, and the response carries our own message plus that reference. Nothing
exception-derived crosses the boundary.

The cost is real and worth stating: you can no longer read the failure cause
straight off the HTTP response, which is a genuine step down for a debugging
tool. The mitigation is that this is a local tool — the log is in the terminal
you started it from, and the reference tells you which line to look at.
"""

from __future__ import annotations

import logging
import uuid

__all__ = ["logged_failure"]


def logged_failure(exc: BaseException, *, logger: logging.Logger, context: str) -> str:
    """Log `exc` in full under a short reference; return a response-safe message.

    `context` is caller-supplied static text, never derived from the exception,
    so the returned string carries no tainted data."""
    ref = uuid.uuid4().hex[:8]
    logger.exception("[%s] %s", ref, context)
    return f"{context} (see server log, ref {ref})"
