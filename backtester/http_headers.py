"""Fail-closed validation for secret-backed HTTP headers."""
from __future__ import annotations

import logging
from collections.abc import Mapping


LOGGER = logging.getLogger(__name__)


def validate_header_values(headers: Mapping[str, tuple[str, str]]) -> None:
    """Log header names and reject non-ASCII values without exposing secrets.

    HTTP clients may defer header encoding until their first network request.  Check
    it at configuration time instead, so deployment errors identify the relevant
    environment variable and never include its value in logs or exceptions.
    """
    for header_name, (value, environment_variable) in headers.items():
        LOGGER.info("Validating HTTP header: %s", header_name)
        try:
            value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError(
                f"{environment_variable} contains non-ASCII characters and cannot be used in an HTTP header."
            ) from exc
