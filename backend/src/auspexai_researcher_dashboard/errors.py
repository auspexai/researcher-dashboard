"""Sanitized error detail for HTTP responses (CodeQL py/stack-trace-exposure).

The dashboard is normally bound to localhost and its "external user" is the
researcher running it, so leaking exception text is mild here — but it stops
being mild the moment someone puts it behind a tunnel, and the diagnostics were
flowing into response bodies verbatim.

**Why this takes no exception argument.** Two earlier shapes both failed to
clear the finding:

1. Returning a truncated ``TypeName: message``. A real improvement — traceback
   to the log, response bounded to one line — but exception-derived data still
   crossed the boundary, and truncating tainted data leaves it tainted.
2. Taking ``exc`` as a parameter and returning only static text plus a random
   reference. Provably clean by reading, but an exception flowing INTO the
   function is enough for the analyzer to treat everything flowing out of it as
   tainted, so the alert survived.

So the exception is never passed in. Call this inside an ``except`` block:
``logger.exception`` picks the active exception up from ``sys.exc_info()`` and
writes it, with traceback, under a short random reference. The returned string
is built only from caller-supplied static text and that reference — there is no
path from the exception to the response, for a reader or an analyzer.

The cost is real and worth stating: the failure cause is no longer readable
straight off the HTTP response, which is a step down for a debugging tool. The
mitigation is that this is a local tool — the log is in the terminal you started
it from, and the reference points at the line.
"""

from __future__ import annotations

import logging
import uuid

__all__ = ["logged_failure"]


def logged_failure(*, logger: logging.Logger, context: str) -> str:
    """Log the ACTIVE exception under a short reference; return a safe message.

    MUST be called from inside an ``except`` block — it relies on
    ``logger.exception`` reading ``sys.exc_info()``. ``context`` is
    caller-supplied static text, never derived from the exception."""
    ref = uuid.uuid4().hex[:8]
    logger.exception("[%s] %s", ref, context)
    return f"{context} (see server log, ref {ref})"
