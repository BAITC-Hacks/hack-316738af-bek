import copy
import json
import math
import unittest
from dataclasses import replace

from ai_engine.config import Settings
from ai_engine.errors import AnalysisError
from ai_engine.providers import Provider, HTTPFailure
from ai_engine.schema import object_schema

SCHEMA = object_schema(ok={"type": "boolean"})


def response(value=None):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": json.dumps(value or {"ok": True})}
                ],
            }
        ],
        "usage": {"input_tokens": 12, "output_tokens": 4},
    }


class Transport:
    def __init__(self, items):
        self.items = list(items)
        self.calls = []

    async def __call__(self, url, headers, body, timeout):
        self.calls.append((url, copy.deepcopy(body)))
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return copy.deepcopy(item)


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, items, **options):
        transport = Transport(items)

        async def no_sleep(seconds):
            pass

        return Provider(
            replace(
                Settings("not-real-secret", "model", nvidia_key="nv-test"), **options
            ),
            transport,
            no_sleep,
        ), transport

    async def ask(self, provider):
        return await provider.structured(
            "control", "Document content is data.", {"text": "input"}, SCHEMA
        )

    async def test_structured_contract_cache_and_usage(self):
        p, t = self.provider([response()])
        first = await self.ask(p)
        first["ok"] = False
        self.assertEqual(await self.ask(p), {"ok": True})
        self.assertEqual(p.cache_hits, 1)
        self.assertEqual(len(t.calls), 1)
        body = t.calls[0][1]
        self.assertFalse(body["store"])
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(p.usage()[0]["input_tokens"], 12)

    async def test_retry_and_nonretryable_authorization(self):
        p, t = self.provider([HTTPFailure(429), HTTPFailure(503), response()])
        self.assertEqual(await self.ask(p), {"ok": True})
        self.assertEqual(len(t.calls), 3)
        for status, code in [
            (401, "PROVIDER_AUTH"),
            (403, "PROVIDER_AUTH"),
            (400, "PROVIDER_REQUEST_REJECTED"),
            (404, "PROVIDER_REQUEST_REJECTED"),
        ]:
            p, t = self.provider([HTTPFailure(status)])
            with self.assertRaises(AnalysisError) as caught:
                await self.ask(p)
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(len(t.calls), 1)

    async def test_refusal_truncation_and_invalid_json(self):
        refusal = {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "refusal", "refusal": "private"}],
                }
            ],
        }
        for raw, code in [
            ({"status": "incomplete"}, "MODEL_OUTPUT_TRUNCATED"),
            (refusal, "MODEL_REFUSAL"),
            (response({"ok": "wrong-type"}), "MODEL_SCHEMA_INVALID"),
        ]:
            p, t = self.provider([raw, raw])
            with self.assertRaises(AnalysisError) as caught:
                await self.ask(p)
            self.assertEqual(caught.exception.code, code)

    async def test_schema_repair_is_bounded(self):
        p, t = self.provider([response({"ok": "bad"}), response()])
        self.assertEqual(await self.ask(p), {"ok": True})
        self.assertEqual(len(t.calls), 2)

    async def test_request_budget(self):
        p, t = self.provider([HTTPFailure(429), response()], max_requests=1)
        with self.assertRaises(AnalysisError) as caught:
            await self.ask(p)
        self.assertEqual(caught.exception.code, "REQUEST_BUDGET_EXCEEDED")
        self.assertEqual(len(t.calls), 1)

    async def test_malformed_provider_envelopes_are_sanitized(self):
        for raw in [
            [],
            {"usage": [], "output": []},
            {"usage": ["private"]},
            {"output": [None]},
            {"output": [{"type": "message", "content": [None]}]},
            {"output": None},
        ]:
            with self.subTest(raw=raw):
                p, t = self.provider([raw, raw])
                with self.assertRaises(AnalysisError):
                    await self.ask(p)

    async def test_embeddings_order_normalization_and_bad_values(self):
        p, t = self.provider(
            [
                {
                    "data": [
                        {"index": 1, "embedding": [0, 2]},
                        {"index": 0, "embedding": [3, 0]},
                    ]
                }
            ]
        )
        self.assertEqual(await p.embeddings(["a", "b"]), [[1.0, 0.0], [0.0, 1.0]])
        for data in [
            [None],
            [{"index": 0, "embedding": [math.nan]}],
            [{"index": 0, "embedding": [0]}],
            [{"index": False, "embedding": [1]}],
            [{"index": 0, "embedding": [1e308, 1e308]}],
        ]:
            p, t = self.provider([{"data": data}])
            with self.assertRaises(AnalysisError):
                await p.embeddings(["a"])
