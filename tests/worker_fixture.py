"""Isolated worker-kill fixture; imported only by the explicit regression subprocess."""

import os
import time
from pathlib import Path

from billiard.exceptions import SoftTimeLimitExceeded

from app.ingestion import tasks

_original_provider = tasks.get_embedding_provider


def blocking_provider(settings):
    marker = os.environ.get("DOCQA_TEST_WORKER_MARKER")
    if marker:
        Path(marker).write_text("embedding started")
        # The test kills this subprocess after observing the committed lease.
        while True:
            try:
                time.sleep(1)
            except SoftTimeLimitExceeded:
                if not os.environ.get("DOCQA_TEST_IGNORE_SOFT_TIMEOUT"):
                    raise
    return _original_provider(settings)


tasks.get_embedding_provider = blocking_provider
