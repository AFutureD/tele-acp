from __future__ import annotations

from typing import Never


def unreachable(message: str) -> Never:
    """Raise an AssertionError with the given message."""
    raise AssertionError(f"Expected code to be unreachable. {message}")


class TeleCLIException(Exception):
    """Base exception class for Tele CLI."""

    pass


class ConfigError(TeleCLIException, ValueError):
    """Exception raised when there is an error in the configuration file."""

    pass


class CurrentSessionPathNotValidError(TeleCLIException, RuntimeError):
    """Exception raised when there is an error during validating the current session path."""

    pass
