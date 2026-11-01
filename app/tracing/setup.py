from __future__ import annotations

import os


def tracing_enabled() -> bool:
    return os.getenv("TRACING_ENABLED", "false").casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
