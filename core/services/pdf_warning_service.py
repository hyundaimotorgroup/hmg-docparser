from __future__ import annotations

import logging


class _WrongPointingObjectWarningFilter(logging.Filter):
    """Hide pypdf's recoverable bad-xref warning, but keep other warnings."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("Ignoring wrong pointing object ")


def suppress_pypdf_wrong_object_warnings() -> None:
    """Silence pypdf warnings emitted while it repairs malformed xref entries."""
    logger = logging.getLogger("pypdf._reader")
    if any(isinstance(item, _WrongPointingObjectWarningFilter) for item in logger.filters):
        return
    logger.addFilter(_WrongPointingObjectWarningFilter())


def suppress_pdf_parser_warnings() -> None:
    """Suppress only pypdf's recoverable bad-xref warnings."""
    suppress_pypdf_wrong_object_warnings()
