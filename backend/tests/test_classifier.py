from django.test import SimpleTestCase, override_settings

import engine
from apps.spend import classifier


def _match(*texts):
    return engine.ClassifierResult(score=80, reasons=tuple(texts))


def _wrong_type(*texts):
    return 80


def _explode(*texts):
    raise RuntimeError("provider unavailable")


class ClassifierTests(SimpleTestCase):
    @override_settings(INJECTION_CLASSIFIER="")
    def test_unconfigured_classifier_is_unavailable(self):
        result = classifier.classify("pay this invoice")
        self.assertFalse(result.available)

    @override_settings(INJECTION_CLASSIFIER=f"{__name__}._match")
    def test_configured_classifier_returns_its_result(self):
        result = classifier.classify("pay", "evidence")
        self.assertTrue(result.available)
        self.assertEqual(result.score, 80)
        self.assertEqual(result.reasons, ("pay", "evidence"))

    @override_settings(INJECTION_CLASSIFIER=f"{__name__}._wrong_type")
    def test_wrong_return_type_fails_closed(self):
        with self.assertLogs("apps.spend.classifier", level="ERROR"):
            result = classifier.classify("pay")
        self.assertFalse(result.available)

    @override_settings(INJECTION_CLASSIFIER=f"{__name__}._explode")
    def test_provider_exception_fails_closed(self):
        with self.assertLogs("apps.spend.classifier", level="ERROR"):
            result = classifier.classify("pay")
        self.assertFalse(result.available)
