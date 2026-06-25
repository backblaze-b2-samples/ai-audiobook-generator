"""Tests for structured logging redaction."""

import json
import logging
import sys

from app.config.logging import JSONFormatter


def test_json_formatter_logs_exception_type_without_message():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        "test",
        logging.ERROR,
        __file__,
        1,
        "operation failed",
        (),
        None,
    )
    try:
        raise RuntimeError("redis://private-host:6379 timed out")
    except RuntimeError:
        record.exc_info = sys.exc_info()

    payload = json.loads(formatter.format(record))

    assert payload["exception"] == "RuntimeError"
    assert "private-host" not in json.dumps(payload)
