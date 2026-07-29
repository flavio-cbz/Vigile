"""
Vigile — Chat API (thin re-export)

Routes defined in sub-modules are registered via import.
Re-exports helpers used by tests for backward compatibility.
"""

from __future__ import annotations

from master.api.chat_router import router

# Import sub-modules to register their routes on the shared router
from master.api import (  # noqa: F401
    chat_helpers,
    chat_proposals,
    chat_sessions,
    chat_stream,
)

# Re-export symbols used by tests
from master.api.chat_helpers import (  # noqa: F401
    MAX_MESSAGE_LENGTH,
    _cap_history,
    _sanitize_message,
    _validate_log_path,
)