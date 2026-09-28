"""Exception hierarchy for gti-copilot.

Every error raised by our own code derives from :class:`GtiError` so callers (the acquisition
loop, the API, the CLI) can distinguish expected operational failures from real bugs.
"""

from __future__ import annotations


class GtiError(Exception):
    """Base class for all gti-copilot errors."""


class ConfigError(GtiError):
    """Invalid or missing configuration."""


class TransportError(GtiError):
    """Communication with the OBD adapter failed (timeout, disconnect, garbage)."""


class NotConnectedError(TransportError):
    """An operation was attempted on a transport that is not connected."""


class ForbiddenServiceError(GtiError):
    """A write / clear / non-allowlisted OBD service was requested.

    This is deliberately *not* a :class:`TransportError`: it is never retried and always
    indicates a programming error (or a tampering attempt), so it must surface loudly.
    """


class DecodeError(GtiError):
    """A PID response could not be decoded (wrong length, unsupported PID)."""


class StorageError(GtiError):
    """SQLite operation failed."""


class ProviderError(GtiError):
    """A GPS / radar / camera / LLM provider is unavailable or misbehaving."""


class PolicyViolation(GtiError):  # noqa: N818 - domain term, not an "Error" per se
    """The driving policy refused an action (e.g. free-form chat while moving)."""
