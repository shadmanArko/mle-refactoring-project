import json
import logging
import sys

from kc_house.api.observability import JsonFormatter


def record(message: str, **extra) -> logging.LogRecord:
    made = logging.LogRecord("kc", logging.ERROR, __file__, 1, message, (), None)
    made.__dict__.update(extra)
    return made


def test_log_lines_are_single_json_objects_with_structured_fields():
    line = JsonFormatter().format(record("request", fields={"status": 200}))

    assert json.loads(line) == {
        "level": "ERROR",
        "logger": "kc",
        "message": "request",
        "status": 200,
    }


def test_errors_carry_their_stack_trace_so_an_outage_can_be_debugged():
    try:
        raise RuntimeError("db is down")
    except RuntimeError:
        failing = record("database error")
        failing.exc_info = sys.exc_info()

    payload = json.loads(JsonFormatter().format(failing))

    assert "RuntimeError: db is down" in payload["exception"]
    assert "\n" not in json.dumps(payload)  # still one line per event
