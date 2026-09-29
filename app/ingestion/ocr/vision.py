"""Vision-LLM OCR (opt-in): the page image goes to an OpenAI-compatible multimodal model
that transcribes it to Markdown. Best structure preservation, no geometry, paid per page
through the budget ledger. Off in the demo by default — the image leaves the server."""

import asyncio
import base64
import concurrent.futures
import contextvars
import io
import re
from collections.abc import Coroutine
from typing import Any

import httpx
from PIL import Image

from app.billing.context import operator_billing
from app.billing.errors import BudgetUnavailableError
from app.billing.providers import after_call, before_call
from app.config import get_settings, is_local_llm_url
from app.ingestion.ocr.base import OcrBlock, OcrError, OcrPage, OcrUnavailableError

_SYSTEM = (
    "You transcribe scanned document pages. Return the page text as Markdown: keep the "
    "reading order, use # headings for titles and section headings, keep lists and "
    "tables (as Markdown tables), preserve numbers and dates exactly. Do not add "
    "commentary, do not translate, do not summarise. If the page is blank, return an "
    "empty response."
)
_MAX_TOKENS = 4096
_HEADING_RE = re.compile(r"^#{1,6}\s+")


def _run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(contextvars.copy_context().run, asyncio.run, coro).result()


class VisionOcr:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self._transport = transport

    @property
    def name(self) -> str:
        return f"vision:{self.model}"

    def recognize(self, image: Image.Image) -> OcrPage:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=85)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        markdown = _run_async(self._transcribe(encoded))
        blocks = [
            OcrBlock(
                text=_HEADING_RE.sub("", block.strip()),
                bbox=None,
                confidence=None,
                line_height=2.0 if _HEADING_RE.match(block.strip()) else 1.0,
                lines=block.strip().splitlines(),
            )
            for block in markdown.split("\n\n")
            if block.strip()
        ]
        return OcrPage(width=image.width, height=image.height, blocks=blocks)

    async def _transcribe(self, encoded_jpeg: str) -> str:
        ticket = None
        if not is_local_llm_url(self.base_url):
            # Text-only reservations cannot bound provider-specific image charges.
            if get_settings().budget_enabled and not operator_billing.get():
                raise BudgetUnavailableError(
                    "Hosted vision OCR has no configured image-token spending bound. "
                    "Use Tesseract for budget-controlled uploads."
                )
            ticket = await before_call(self.model, [_SYSTEM], _MAX_TOKENS)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": _MAX_TOKENS,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Transcribe this page."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{encoded_jpeg}"},
                        },
                    ],
                },
            ],
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_s, connect=10.0), transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=headers
                )
        except httpx.HTTPError as exc:
            raise OcrUnavailableError(f"vision OCR request failed: {exc}") from exc
        if response.status_code != 200:
            raise OcrUnavailableError(
                f"vision OCR returned {response.status_code}: {response.text[:200]}"
            )
        try:
            body = response.json()
            usage = body.get("usage") or {}
            await after_call(
                ticket, self.model, usage.get("prompt_tokens"), usage.get("completion_tokens")
            )
            content = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise OcrError(f"vision OCR returned an unexpected payload: {exc}") from exc
        return str(content or "")
