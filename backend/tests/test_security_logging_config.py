"""Tests for the agentgate.security account-security audit logger (AUTH-05B.9C.1).

These tests verify the *logging configuration* declared in
``config.settings.base`` — not any specific security event — using only
synthetic messages and safe metadata.
"""

import io
import json
import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.test import SimpleTestCase, override_settings


class SecurityLoggerConfigTests(SimpleTestCase):
    """Verify the agentgate.security logger is correctly configured in settings."""

    # --- A. agentgate.security logger is configured ---

    def test_logger_registered_in_settings(self):
        self.assertIn("agentgate.security", settings.LOGGING["loggers"])

    def test_logger_level_is_info(self):
        logger_cfg = settings.LOGGING["loggers"]["agentgate.security"]
        self.assertEqual(logger_cfg["level"], "INFO")

    def test_logger_assigned_security_handler(self):
        logger_cfg = settings.LOGGING["loggers"]["agentgate.security"]
        self.assertIn("security", logger_cfg["handlers"])

    def test_logger_propagation_disabled(self):
        """No duplicate propagation to the root logger."""
        logger_cfg = settings.LOGGING["loggers"]["agentgate.security"]
        self.assertFalse(logger_cfg.get("propagate", True))

    # --- Handler: StreamHandler → stderr with no debug filters ---

    def test_security_handler_configured(self):
        self.assertIn("security", settings.LOGGING["handlers"])
        handler_cfg = settings.LOGGING["handlers"]["security"]
        self.assertEqual(handler_cfg["class"], "logging.StreamHandler")
        self.assertEqual(handler_cfg["level"], "INFO")

    def test_security_handler_has_no_filters(self):
        """F. DEBUG=False does not suppress INFO events (no debug gates)."""
        handler_cfg = settings.LOGGING["handlers"]["security"]
        self.assertNotIn("filters", handler_cfg)

    def test_security_handler_has_no_explicit_stderr_stream(self):
        """StreamHandler with no *stream* key defaults to sys.stderr."""
        handler_cfg = settings.LOGGING["handlers"]["security"]
        self.assertNotIn("stream", handler_cfg)

    # --- Formatter: structured JSON output ---

    def test_json_formatter_factory_registered(self):
        self.assertIn("security_json", settings.LOGGING["formatters"])
        formatter_cfg = settings.LOGGING["formatters"]["security_json"]
        self.assertIn("()", formatter_cfg)

    # --- G. No unrelated logger configuration is broken ---

    def test_disable_existing_loggers_preserved(self):
        self.assertFalse(settings.LOGGING.get("disable_existing_loggers", True))

    def test_django_default_loggers_preserved(self):
        loggers = settings.LOGGING["loggers"]
        self.assertIn("django", loggers)
        self.assertIn("django.server", loggers)

    def test_django_default_handlers_preserved(self):
        handlers = settings.LOGGING["handlers"]
        self.assertIn("console", handlers)
        self.assertIn("django.server", handlers)

    def test_django_default_formatters_preserved(self):
        formatters = settings.LOGGING["formatters"]
        self.assertIn("django.server", formatters)


class SecurityLoggerRuntimeTests(SimpleTestCase):
    """Verify runtime behavior of the agentgate.security logger."""

    def setUp(self):
        self.logger = logging.getLogger("agentgate.security")
        self._saved_handlers = self.logger.handlers[:]
        self._saved_level = self.logger.level
        self._saved_propagate = self.logger.propagate

        self.stream = io.StringIO()
        self.capture = logging.StreamHandler(self.stream)
        for h in self._saved_handlers:
            if h.formatter:
                self.capture.setFormatter(h.formatter)
                break
        self.capture.setLevel(logging.DEBUG)

        self.logger.handlers = [self.capture]
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

    def tearDown(self):
        self.logger.handlers = self._saved_handlers
        self.logger.level = self._saved_level
        self.logger.propagate = self._saved_propagate
        super().tearDown()

    def _records(self):
        content = self.stream.getvalue().strip()
        if not content:
            return []
        return [json.loads(line) for line in content.splitlines() if line.strip()]

    # --- A. logger actually configured at runtime ---

    def test_logger_has_handlers_at_startup(self):
        self.assertTrue(self._saved_handlers)
        self.assertIn("agentgate.security", settings.LOGGING["loggers"])

    # --- B / C. INFO and WARNING emitted as valid JSON ---

    def test_info_event_emitted_as_json(self):
        self.logger.info("synthetic security audit: info event")
        records = self._records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["level"], "INFO")
        self.assertEqual(records[0]["logger"], "agentgate.security")
        self.assertEqual(records[0]["message"], "synthetic security audit: info event")

    def test_warning_event_emitted_as_json(self):
        self.logger.warning("synthetic security audit: warning event")
        records = self._records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["level"], "WARNING")

    # --- C. Each event is valid JSON ---

    def test_single_line_json_per_event(self):
        self.logger.info("first safe event")
        self.logger.warning("second safe event")
        lines = [
            line
            for line in self.stream.getvalue().strip().splitlines()
            if line.strip()
        ]
        self.assertEqual(len(lines), 2)
        for line in lines:
            obj = json.loads(line)
            self.assertIsInstance(obj, dict)

    # --- D. Timestamp is UTC ---

    def test_timestamp_is_utc(self):
        self.logger.info("utc timestamp check")
        records = self._records()
        self.assertEqual(len(records), 1)
        parsed = datetime.fromisoformat(records[0]["timestamp"])
        self.assertEqual(parsed.utcoffset(), timedelta(0))

    # --- E. Each event emitted once (no duplicate propagation) ---

    def test_event_emitted_exactly_once(self):
        self.logger.propagate = False
        self.logger.info("single emission check")
        records = self._records()
        self.assertEqual(len(records), 1)

    # --- F. DEBUG=False does not suppress INFO ---

    @override_settings(DEBUG=False)
    def test_info_not_suppressed_with_debug_false(self):
        self.logger.info("info despite debug=false")
        records = self._records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["level"], "INFO")

    # --- No exception serialization ---

    def test_no_exception_traceback_in_output(self):
        try:
            raise ValueError("sensitive internal detail")
        except ValueError:
            self.logger.info("event with exception context")
        records = self._records()
        self.assertEqual(len(records), 1)
        serialized = json.dumps(records[0])
        self.assertNotIn("sensitive internal detail", serialized)
        self.assertNotIn("exc_info", records[0])

    # --- No sensitive metadata auto-serialized ---

    def test_no_request_fields_in_output(self):
        self.logger.info("request safety check")
        records = self._records()
        self.assertEqual(len(records), 1)
        record_keys = set(records[0].keys())
        for forbidden in ("request", "cookies", "headers", "body", "exc_text"):
            self.assertNotIn(forbidden, record_keys)
