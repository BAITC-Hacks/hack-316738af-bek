"""Bounded OpenAI/NVIDIA HTTP clients with injectable transport for tests."""

import asyncio
import copy
import hashlib
import json
import math
import time
import urllib.error
import urllib.request

from .errors import AnalysisError
from .schema import validate_model

OPENAI_URL = "https://api.openai.com/v1/responses"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/embeddings"


def compact_sources(payload):
    """Use short wire labels; keep public/source registry identifiers untouched."""
    wire = copy.deepcopy(payload)
    forward = {s["id"]: f"S{i + 1}" for i, s in enumerate(wire["sources"])}
    for source in wire["sources"]:
        source["id"] = forward[source["id"]]
    wire["target_span_ids"] = [forward[sid] for sid in wire["target_span_ids"]]
    return wire, {alias: original for original, alias in forward.items()}


def expand_sources(value, reverse):
    """Expand reference fields only; never rewrite names, prose or entity IDs."""
    for item in value["units"] + value["functions"]:
        for field in ("source_span_ids", "context_span_ids"):
            if field in item:
                item[field] = [reverse.get(sid, sid) for sid in item[field]]
        for quote in item["evidence_quotes"]:
            quote["span_id"] = reverse.get(quote["span_id"], quote["span_id"])
    for item in value["coverage"]:
        item["span_id"] = reverse.get(item["span_id"], item["span_id"])
    return value


def map_reference_fields(value, transform):
    """Map typed identifier fields while leaving document prose untouched."""
    if isinstance(value, list):
        return [map_reference_fields(item, transform) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if (key == "id" or key.endswith("_id")) and isinstance(item, str):
            result[key] = transform(item)
        elif key.endswith("_ids") and isinstance(item, list):
            result[key] = [transform(s) if isinstance(s, str) else s for s in item]
        else:
            result[key] = map_reference_fields(item, transform)
    return result


def compact_references(payload):
    forward = {}

    def label(original):
        if original not in forward:
            forward[original] = f"R{len(forward) + 1}"
        return forward[original]

    wire = map_reference_fields(payload, label)
    return wire, {alias: original for original, alias in forward.items()}


class HTTPFailure(Exception):
    def __init__(self, status, retry_after=0):
        self.status = status
        self.retry_after = retry_after
        super().__init__(f"HTTP {status}")


def _http_post(url, headers, payload, timeout):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise AnalysisError(
                    "PROVIDER_RESPONSE_TOO_LARGE", "AI сервисінің жауабы тым үлкен."
                )
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        # Never read or expose error bodies; they can contain request information.
        try:
            delay = min(10, max(0, float(exc.headers.get("Retry-After", "0"))))
        except (ValueError, TypeError):
            delay = 0
        raise HTTPFailure(exc.code, delay) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise HTTPFailure(0) from None
    except (UnicodeError, json.JSONDecodeError):
        raise AnalysisError(
            "PROVIDER_JSON_INVALID", "AI сервисі жарамсыз JSON қайтарды.", True
        ) from None


async def default_transport(url, headers, payload, timeout):
    return await asyncio.to_thread(_http_post, url, headers, payload, timeout)


class Provider:
    def __init__(self, settings, transport=None, sleep=asyncio.sleep):
        self.settings = settings
        self.transport = transport or default_transport
        self.sleep = sleep
        self.semaphore = asyncio.Semaphore(settings.concurrency)
        self.requests = 0
        self.cache_hits = 0
        self.cache = {}
        self._usage = {}

    def usage(self):
        return copy.deepcopy(list(self._usage.values()))

    async def _post(self, provider, model, url, key, body):
        meter = self._usage.setdefault(
            (provider, model),
            {
                "provider": provider,
                "model": model,
                "input_tokens": 0,
                "output_tokens": 0,
                "calls": 0,
                "elapsed_ms": 0,
            },
        )
        for attempt in range(self.settings.retries + 1):
            try:
                async with self.semaphore:
                    if self.requests >= self.settings.max_requests:
                        raise AnalysisError(
                            "REQUEST_BUDGET_EXCEEDED",
                            "AI сұрауларының лимиті аяқталды.",
                        )
                    self.requests += 1
                    meter["calls"] += 1
                    start = time.monotonic()
                    try:
                        response = await asyncio.wait_for(
                            self.transport(
                                url,
                                {"Authorization": "Bearer " + key},
                                body,
                                self.settings.request_timeout,
                            ),
                            timeout=self.settings.request_timeout + 1,
                        )
                    finally:
                        meter["elapsed_ms"] += int((time.monotonic() - start) * 1000)
                if not isinstance(response, dict):
                    raise AnalysisError(
                        "PROVIDER_JSON_INVALID",
                        "AI сервисінің жауап құрылымы жарамсыз.",
                        True,
                    )
                usage = response.get("usage") or {}
                if not isinstance(usage, dict):
                    raise AnalysisError(
                        "PROVIDER_JSON_INVALID",
                        "AI сервисінің токен есебі жарамсыз.",
                        True,
                    )
                inp = usage.get("input_tokens", usage.get("prompt_tokens"))
                out = usage.get("output_tokens", 0 if provider == "nvidia" else None)
                for field, value in (("input_tokens", inp), ("output_tokens", out)):
                    if (
                        isinstance(value, int)
                        and not isinstance(value, bool)
                        and value >= 0
                        and meter[field] is not None
                    ):
                        meter[field] += value
                    else:
                        meter[field] = None
                return response
            except asyncio.CancelledError:
                raise
            except (HTTPFailure, asyncio.TimeoutError) as exc:
                # An interrupted request may still have consumed tokens remotely.
                meter["input_tokens"] = meter["output_tokens"] = None
                status = getattr(exc, "status", 0)
                if status in (401, 403):
                    raise AnalysisError(
                        "PROVIDER_AUTH",
                        "AI сервисі кілтті немесе қолжетімділікті қабылдамады.",
                    ) from None
                if status in (400, 404, 422):
                    raise AnalysisError(
                        "PROVIDER_REQUEST_REJECTED",
                        "Модель атауы немесе AI сұрауы қабылданбады.",
                    ) from None
                retryable = status == 0 or status == 429 or status >= 500
                if not retryable or attempt == self.settings.retries:
                    raise AnalysisError(
                        "PROVIDER_UNAVAILABLE",
                        "AI сервисі уақытында жауап бермеді немесе уақытша қолжетімсіз.",
                        retryable,
                    ) from None
                await self.sleep(
                    max(getattr(exc, "retry_after", 0), min(4, 0.5 * (2**attempt)))
                )
        raise AssertionError("unreachable")

    async def structured(self, operation, instructions, payload, schema):
        self.settings.require_live()
        cache_key = hashlib.sha256(
            json.dumps(
                [self.settings.model, operation, instructions, payload, schema],
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            ).encode()
        ).hexdigest()
        if cache_key in self.cache:
            self.cache_hits += 1
            return copy.deepcopy(self.cache[cache_key])
        wire_payload, source_aliases = (
            compact_sources(payload)
            if operation == "extract_functions"
            else compact_references(payload)
        )
        body = {
            "model": self.settings.model,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                wire_payload, ensure_ascii=False, allow_nan=False
                            ),
                        }
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": operation,
                    "strict": True,
                    "schema": schema,
                }
            },
            "max_output_tokens": self.settings.max_output_tokens,
            "store": False,
        }
        # Evidence analysis benefits from low sampling variance. Restrict this
        # setting to model families that support it; reasoning models may not.
        if self.settings.model.startswith(("gpt-4.1", "gpt-4o")):
            body["temperature"] = 0
        for attempt in range(2):
            response = await self._post(
                "openai", self.settings.model, OPENAI_URL, self.settings.api_key, body
            )
            if response.get("status") == "incomplete":
                raise AnalysisError(
                    "MODEL_OUTPUT_TRUNCATED",
                    "AI жауабы толық аяқталмады; нәтиже толық деп көрсетілмейді.",
                    True,
                )
            if response.get("status") != "completed" or response.get("error"):
                raise AnalysisError(
                    "MODEL_RESPONSE_FAILED", "AI талдауы аяқталмады.", True
                )
            pieces = []
            output = response.get("output", [])
            if not isinstance(output, list):
                raise AnalysisError(
                    "PROVIDER_JSON_INVALID",
                    "AI сервисінің шығыс құрылымы жарамсыз.",
                    True,
                )
            for item in output:
                if not isinstance(item, dict):
                    raise AnalysisError(
                        "PROVIDER_JSON_INVALID",
                        "AI сервисінің хабарламасы жарамсыз.",
                        True,
                    )
                if item.get("type") != "message":
                    continue
                contents = item.get("content", [])
                if not isinstance(contents, list):
                    raise AnalysisError(
                        "PROVIDER_JSON_INVALID",
                        "AI хабарламасының мазмұны жарамсыз.",
                        True,
                    )
                for content in contents:
                    if not isinstance(content, dict):
                        raise AnalysisError(
                            "PROVIDER_JSON_INVALID",
                            "AI хабарламасының бөлігі жарамсыз.",
                            True,
                        )
                    if content.get("type") == "refusal":
                        raise AnalysisError(
                            "MODEL_REFUSAL", "AI берілген сұрауды өңдеуден бас тартты."
                        )
                    if content.get("type") == "output_text":
                        pieces.append(content.get("text", ""))
            try:
                value = json.loads("".join(pieces))
                validate_model(schema, value)
            except (json.JSONDecodeError, TypeError, AnalysisError):
                if attempt == 1:
                    raise AnalysisError(
                        "MODEL_SCHEMA_INVALID",
                        "AI жауабы екі әрекеттен кейін де схемаға сәйкес емес.",
                        True,
                    ) from None
                body["instructions"] = (
                    instructions
                    + "\nReturn exactly the requested JSON object with every required field."
                )
                continue
            if source_aliases:
                value = (
                    expand_sources(value, source_aliases)
                    if operation == "extract_functions"
                    else map_reference_fields(
                        value, lambda sid: source_aliases.get(sid, sid)
                    )
                )
            self.cache[cache_key] = copy.deepcopy(value)
            return value
        raise AssertionError("unreachable")

    async def embeddings(self, texts, input_type="passage"):
        if input_type not in ("passage", "query"):
            raise AnalysisError(
                "EMBEDDING_INPUT_INVALID", "Embedding input_type жарамсыз."
            )
        if not texts:
            return []
        if not self.settings.nvidia_key:
            raise AnalysisError("NVIDIA_KEY_MISSING", "NVIDIA_API_KEY орнатылмаған.")
        response = await self._post(
            "nvidia",
            self.settings.nvidia_model,
            NVIDIA_URL,
            self.settings.nvidia_key,
            {
                "model": self.settings.nvidia_model,
                "input": texts,
                "input_type": input_type,
                "encoding_format": "float",
                "truncate": "NONE",
            },
        )
        data = response.get("data", [])
        if not isinstance(data, list) or len(data) != len(texts):
            raise AnalysisError(
                "EMBEDDING_INVALID", "Embedding саны кіріске сәйкес емес."
            )
        ordered = [None] * len(texts)
        for item in data:
            if not isinstance(item, dict):
                raise AnalysisError(
                    "EMBEDDING_INVALID", "Embedding объектісі жарамсыз."
                )
            i, vector = item.get("index"), item.get("embedding")
            if (
                not isinstance(i, int)
                or isinstance(i, bool)
                or not 0 <= i < len(texts)
                or ordered[i] is not None
            ):
                raise AnalysisError(
                    "EMBEDDING_INVALID", "Embedding индекстері жарамсыз."
                )
            if (
                not isinstance(vector, list)
                or not vector
                or any(
                    not isinstance(x, (float, int))
                    or isinstance(x, bool)
                    or not math.isfinite(x)
                    for x in vector
                )
            ):
                raise AnalysisError("EMBEDDING_INVALID", "Embedding векторы жарамсыз.")
            norm = math.sqrt(sum(x * x for x in vector))
            if not norm or not math.isfinite(norm):
                raise AnalysisError("EMBEDDING_INVALID", "Embedding векторы нөлге тең.")
            ordered[i] = [x / norm for x in vector]
        if len({len(x) for x in ordered}) != 1:
            raise AnalysisError("EMBEDDING_INVALID", "Embedding өлшемдері әртүрлі.")
        return ordered
