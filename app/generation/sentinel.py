"""NO_ANSWER interception.

The model may reply with the refusal sentinel instead of an answer. We must not leak it
to the client as a delta, so the first few characters are buffered until the stream is
provably not the sentinel; only then does text flow through.
"""


class SentinelBuffer:
    def __init__(self, sentinel: str = "NO_ANSWER") -> None:
        self._sentinel = sentinel
        self._buffer = ""
        self._decided = False
        self.refused = False

    def feed(self, text: str) -> str:
        """Returns the text safe to emit now ('' while the verdict is still open)."""
        if self._decided:
            return "" if self.refused else text
        self._buffer += text
        stripped = self._buffer.lstrip()
        if stripped.startswith(self._sentinel):
            self._decided = True
            self.refused = True
            return ""
        if not self._sentinel.startswith(stripped[: len(self._sentinel)]):
            # can no longer become the sentinel — release everything buffered
            self._decided = True
            out = self._buffer
            self._buffer = ""
            return out
        return ""  # still an ambiguous prefix ("NO_ANS…")

    def flush(self) -> str:
        """Call at stream end: releases a pending buffer that never became the sentinel."""
        if self._decided or not self._buffer:
            return ""
        self._decided = True
        out = self._buffer
        self._buffer = ""
        return out
