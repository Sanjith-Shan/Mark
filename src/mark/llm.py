"""LLM wrapper: structured outputs, free-form text, embeddings, retries, cost.

Every agent goes through this module instead of touching the OpenAI SDK directly.
Benefits:

* One place for exponential-backoff retry on transient errors.
* Token usage + estimated USD is logged to the ``costs`` table on every call.
* A deterministic offline path (when no ``OPENAI_API_KEY``) so the whole pipeline
  runs without spending anything. Agents pass a ``mock_factory`` to produce
  meaningful offline output; embeddings fall back to a stable hash-based vector
  whose cosine geometry is good enough for dedup and winner retrieval.
"""

from __future__ import annotations

import hashlib
import time
from typing import Callable, Optional, TypeVar

import numpy as np
from pydantic import BaseModel

from .app import App
from . import db as db_module

T = TypeVar("T", bound=BaseModel)

EMBED_DIM = 256  # dimension used for the offline hash embedding

# Approximate prices (USD). Kept here as a single source of truth; update freely.
# Text models priced per 1M tokens (input, output). Verified July 2026.
_TEXT_PRICES = {
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
}
_EMBED_PRICE_PER_M = {"text-embedding-3-small": 0.02, "text-embedding-3-large": 0.13}
_IMAGE_PRICE = {  # per image by quality (gpt-image-1.5, portrait/landscape sizes)
    "low": 0.013, "medium": 0.05, "high": 0.20,
}
_TTS_PRICE_PER_M_CHARS = 15.0  # ≈ tts-1 / gpt-4o-mini-tts effective per-char rate


class LLM:
    def __init__(self, app: App):
        self.app = app
        self._client = None

    # -- availability ----------------------------------------------------- #
    @property
    def mock(self) -> bool:
        return self.app.is_mock("openai")

    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.app.keys.openai)
        return self._client

    # -- structured output ------------------------------------------------ #
    def parse(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        model: Optional[str] = None,
        temperature: float = 0.9,
        mock_factory: Optional[Callable[[], T]] = None,
        content_id: Optional[int] = None,
        product_id: Optional[str] = None,
    ) -> T:
        """Return a validated instance of ``schema`` from the model."""
        if self.mock:
            obj = mock_factory() if mock_factory else _empty_instance(schema)
            self._log_cost("openai", "chat", model or self.app.settings.llm.text_model,
                           content_id, product_id, mocked=True)
            return obj

        model = model or self.app.settings.llm.text_model
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

        def _call():
            return self.client().beta.chat.completions.parse(
                model=model, messages=messages, response_format=schema, temperature=temperature
            )

        completion = _retry(_call)
        usage = getattr(completion, "usage", None)
        self._log_cost(
            "openai", "chat", model, content_id, product_id,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:  # refusal or empty — fall back to a safe empty object
            return mock_factory() if mock_factory else _empty_instance(schema)
        return parsed

    # -- free-form text --------------------------------------------------- #
    def text(
        self,
        system: str,
        user: str,
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        mock_text: str = "",
        content_id: Optional[int] = None,
        product_id: Optional[str] = None,
    ) -> str:
        if self.mock:
            self._log_cost("openai", "chat", model or self.app.settings.llm.text_model,
                           content_id, product_id, mocked=True)
            return mock_text

        model = model or self.app.settings.llm.text_model
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

        def _call():
            return self.client().chat.completions.create(
                model=model, messages=messages, temperature=temperature
            )

        completion = _retry(_call)
        usage = getattr(completion, "usage", None)
        self._log_cost(
            "openai", "chat", model, content_id, product_id,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
        return completion.choices[0].message.content or ""

    # -- embeddings ------------------------------------------------------- #
    def embed(self, texts: list[str], *, content_id: Optional[int] = None,
              product_id: Optional[str] = None) -> np.ndarray:
        """Return an (n, d) float32 array of embeddings."""
        if not texts:
            return np.zeros((0, EMBED_DIM), dtype=np.float32)
        if self.mock:
            self._log_cost("openai", "embedding", "mock-hash", content_id, product_id, mocked=True)
            return np.stack([_hash_embedding(t) for t in texts])

        model = self.app.settings.llm.embedding_model

        def _call():
            return self.client().embeddings.create(model=model, input=texts)

        resp = _retry(_call)
        vectors = np.array([d.embedding for d in resp.data], dtype=np.float32)
        total_tokens = getattr(getattr(resp, "usage", None), "total_tokens", 0) or 0
        self._log_cost("openai", "embedding", model, content_id, product_id,
                       input_tokens=total_tokens)
        return vectors

    def embed_one(self, text: str, **kw) -> np.ndarray:
        return self.embed([text], **kw)[0]

    # -- cost logging ----------------------------------------------------- #
    def _log_cost(self, provider, operation, model, content_id, product_id,
                  input_tokens=0, output_tokens=0, units=0.0, mocked=False):
        usd = 0.0 if mocked else estimate_cost(operation, model, input_tokens, output_tokens, units)
        try:
            db_module.insert(
                self.app.conn, "costs",
                provider=provider, operation=operation, model=str(model),
                content_id=content_id, product_id=product_id,
                input_tokens=int(input_tokens), output_tokens=int(output_tokens),
                units=float(units), usd=float(usd), mocked=1 if mocked else 0,
            )
        except Exception:
            # Cost logging must never break the pipeline.
            pass


# --------------------------------------------------------------------------- #
# Cost estimation (shared so media/posting modules can log too)
# --------------------------------------------------------------------------- #
def estimate_cost(operation: str, model: str, input_tokens: int = 0,
                  output_tokens: int = 0, units: float = 0.0) -> float:
    if operation == "chat":
        prices = _TEXT_PRICES.get(model, (2.5, 10.0))
        return (input_tokens / 1_000_000) * prices[0] + (output_tokens / 1_000_000) * prices[1]
    if operation == "embedding":
        per_m = _EMBED_PRICE_PER_M.get(model, 0.02)
        return (input_tokens / 1_000_000) * per_m
    if operation == "image":
        # `model` carries the quality here ("low"/"medium"/"high"); units = #images.
        return _IMAGE_PRICE.get(model, 0.06) * max(units, 1.0)
    if operation == "tts":
        return (units / 1_000_000) * _TTS_PRICE_PER_M_CHARS
    if operation == "video":
        return units  # caller passes pre-computed USD as units for video
    return 0.0


def log_external_cost(app: App, provider: str, operation: str, model: str,
                      usd: float = 0.0, units: float = 0.0, content_id=None,
                      product_id=None, mocked: bool = False) -> None:
    """Helper for non-LLM providers (fal, tts, upload-post) to record spend."""
    try:
        db_module.insert(
            app.conn, "costs",
            provider=provider, operation=operation, model=str(model),
            content_id=content_id, product_id=product_id,
            units=float(units), usd=float(0.0 if mocked else usd),
            mocked=1 if mocked else 0,
        )
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Retry + offline helpers
# --------------------------------------------------------------------------- #
def _retry(fn: Callable, attempts: int = 3, base_delay: float = 1.5):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - we genuinely want to retry anything transient
            last = exc
            if i == attempts - 1:
                break
            time.sleep(base_delay * (2 ** i))
    raise last  # type: ignore[misc]


def _hash_embedding(text: str) -> np.ndarray:
    """Deterministic pseudo-embedding. Identical text -> identical vector; cosine
    geometry is stable enough for dedup and nearest-winner retrieval offline."""
    seed = int.from_bytes(hashlib.sha256(text.strip().lower().encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(EMBED_DIM).astype(np.float32)
    n = np.linalg.norm(v)
    return v / n if n else v


def _empty_instance(schema: type[T]) -> T:
    """Construct a schema instance with type-appropriate empty values.

    Last-resort offline fallback when an agent didn't supply a ``mock_factory``.
    """
    values = {}
    for name, field in schema.model_fields.items():
        if not field.is_required():
            continue
        ann = field.annotation
        values[name] = _zero_for(ann)
    return schema.model_construct(**values) if values else schema()  # type: ignore[call-arg]


def _zero_for(annotation) -> object:
    origin = getattr(annotation, "__origin__", None)
    if annotation is str:
        return ""
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    if annotation is bool:
        return False
    if origin in (list, tuple, set):
        return []
    if origin is dict:
        return {}
    return None
