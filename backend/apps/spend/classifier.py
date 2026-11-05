"""Runs the configured advisory injection classifier with a hard deadline."""

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from django.conf import settings
from django.utils.module_loading import import_string

import engine

logger = logging.getLogger(__name__)


def _run(path: str, texts: tuple[str, ...]) -> engine.ClassifierResult:
    classifier = import_string(path)
    result = classifier(*texts)
    if not isinstance(result, engine.ClassifierResult):
        raise TypeError("Injection classifier must return ClassifierResult.")
    return result


def classify(*texts: str) -> engine.ClassifierResult:
    """Return classifier output, or an unavailable result on any failure."""
    path = getattr(settings, "INJECTION_CLASSIFIER", "").strip()
    if not path:
        return engine.ClassifierResult()

    timeout = getattr(settings, "INJECTION_CLASSIFIER_TIMEOUT_SECONDS", 2)
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_run, path, texts)
        return future.result(timeout=timeout)
    except FutureTimeout:
        logger.warning("Injection classifier timed out.")
        return engine.ClassifierResult()
    except Exception:
        logger.exception("Injection classifier failed.")
        return engine.ClassifierResult()
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
