from __future__ import annotations

import json
import logging
from pathlib import Path

from gti_copilot.logging import JsonFormatter, TextFormatter, get_logger, setup_logging


def _record(msg: str, **extra: object) -> logging.LogRecord:
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def test_json_formatter_includes_extras() -> None:
    out = json.loads(JsonFormatter().format(_record("hello", device="/dev/x", n=3)))
    assert out["msg"] == "hello"
    assert out["device"] == "/dev/x"
    assert out["n"] == 3
    assert out["level"] == "INFO"


def test_text_formatter_appends_extras() -> None:
    text = TextFormatter().format(_record("hello", a=1))
    assert text.endswith("hello a=1")


def test_setup_logging_with_file(tmp_path: Path) -> None:
    log_file = tmp_path / "sub" / "gti.log"
    setup_logging(level="DEBUG", json_output=True, file=log_file)
    get_logger("gti_copilot.test").info("written", extra={"k": "v"})
    for h in logging.getLogger().handlers:
        h.flush()
    assert '"k":"v"' in log_file.read_text()
    setup_logging()  # reset to defaults; must not raise when called twice
