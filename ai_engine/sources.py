"""Immutable source registry and boundary checks before any paid API call."""

import copy
import hashlib
import json
import re
import unicodedata

from .errors import AnalysisError
from .schema import validate


def normalize(text):
    text = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    return re.sub(r"\s+", " ", text).strip()


def stable_id(prefix, *parts):
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + "_" + hashlib.sha256(raw.encode()).hexdigest()[:20]


def unique(values):
    return list(dict.fromkeys(values))


def diagnostic(code, message, document_id=None, span_ids=()):
    return {
        "code": code,
        "message": message,
        "document_id": document_id,
        "span_ids": list(span_ids),
    }


class SourceRegistry:
    def __init__(self, payload, max_chars=1200000):
        validate("AnalysisInput", payload)
        self.payload = copy.deepcopy(payload)
        self.docs = {}
        self.spans = {}
        self.warnings = []
        size = 0
        for doc in self.payload["documents"]:
            if not doc["id"] or doc["id"] in self.docs:
                raise AnalysisError(
                    "DOCUMENT_ID_DUPLICATE",
                    "Құжат идентификаторы бос немесе қайталанған.",
                )
            self.docs[doc["id"]] = doc
            if doc["parse_status"] == "pending":
                raise AnalysisError(
                    "PARSING_PENDING", "Құжаттарды оқу аяқталмаған.", True
                )
            if doc["span_count"] != len(doc["spans"]):
                raise AnalysisError(
                    "SPAN_COUNT_MISMATCH", "Құжат үзінділерінің саны сәйкес емес."
                )
            self.warnings.extend(doc["warnings"])
            for span in doc["spans"]:
                if not span["id"] or span["id"] in self.spans:
                    raise AnalysisError(
                        "SPAN_ID_DUPLICATE",
                        "Үзінді идентификаторы бос немесе қайталанған.",
                    )
                if span["document_id"] != doc["id"]:
                    raise AnalysisError(
                        "SOURCE_DOCUMENT_MISMATCH",
                        "Үзінді басқа құжатқа байланыстырылған.",
                    )
                self.spans[span["id"]] = span
                size += len(span["raw_text"])
            if doc["parse_status"] in ("partial", "failed"):
                self.warnings.append(
                    diagnostic(
                        "DOCUMENT_INCOMPLETE",
                        "Құжат толық оқылмаған; қорытындының қамтуы шектеулі.",
                        doc["id"],
                    )
                )
        if size > max_chars:
            raise AnalysisError(
                "INPUT_TOO_LARGE",
                "Талдау көлемі engine шегінен асты; материал үнсіз қысқартылмады.",
            )
        for span in self.spans.values():
            for parent in span["context_span_ids"]:
                if (
                    parent not in self.spans
                    or self.spans[parent]["document_id"] != span["document_id"]
                ):
                    raise AnalysisError(
                        "SOURCE_CONTEXT_INVALID",
                        "Тақырып контекстінің сілтемесі жарамсыз.",
                    )
        # Iterative DFS also handles deep, hostile inputs without recursion overflow.
        colors = {}
        for start in self.spans:
            stack = [(start, False)]
            while stack:
                node, leaving = stack.pop()
                if leaving:
                    colors[node] = 2
                    continue
                if colors.get(node) == 1:
                    raise AnalysisError(
                        "SOURCE_CONTEXT_CYCLE", "Дереккөз контекстінде цикл бар."
                    )
                if colors.get(node) == 2:
                    continue
                colors[node] = 1
                stack.append((node, True))
                stack.extend(
                    (p, False) for p in reversed(self.spans[node]["context_span_ids"])
                )
        for version in ("before", "after"):
            if not any(
                d["version"] == version
                and d["parse_status"] in ("complete", "partial")
                and any(s["is_content"] and s["raw_text"].strip() for s in d["spans"])
                for d in self.docs.values()
            ):
                raise AnalysisError(
                    "VERSION_EMPTY", f"{version} тобында оқылған мәтін жоқ."
                )

    def version(self, span_id):
        return self.docs[self.spans[span_id]["document_id"]]["version"]

    def ids(self, ids, version=None, nonempty=False):
        if not isinstance(ids, list) or (nonempty and not ids):
            raise AnalysisError(
                "EVIDENCE_INVALID", "Қорытындының дәлелі жоқ немесе жарамсыз."
            )
        for sid in ids:
            if sid not in self.spans or (version and self.version(sid) != version):
                raise AnalysisError(
                    "EVIDENCE_INVALID", "Дереккөз сілтемесі осы нұсқаға тиесілі емес."
                )
        return unique(ids)

    def context_ids(self, ids):
        result = set()
        stack = list(ids)
        while stack:
            sid = stack.pop()
            for parent in self.spans[sid]["context_span_ids"]:
                if parent not in result:
                    result.add(parent)
                    stack.append(parent)
        return sorted(result)

    def evidence(self, ids, include_context=True):
        ids = self.ids(list(ids))
        if include_context:
            ids = unique(ids + self.context_ids(ids))
        return [
            {
                "id": sid,
                "document_id": self.spans[sid]["document_id"],
                "version": self.version(sid),
                "section_path": self.spans[sid]["section_path"],
                "raw_text": self.spans[sid]["raw_text"],
            }
            for sid in ids
        ]

    def complete(self, version):
        return all(
            d["parse_status"] == "complete"
            for d in self.docs.values()
            if d["version"] == version
        )

    def doc_ids(self, version):
        return [d["id"] for d in self.docs.values() if d["version"] == version]

    def summaries(self):
        return [
            {k: copy.deepcopy(v) for k, v in d.items() if k != "spans"}
            for d in self.docs.values()
        ]

    def quote_valid(self, span_id, quote):
        return (
            span_id in self.spans
            and bool(quote.strip())
            and normalize(quote) in normalize(self.spans[span_id]["raw_text"])
        )


def pack_chunks(items, max_chars, formatter=lambda x: x):
    """Cover every item; never silently slice text or skip oversized spans."""
    current, count = [], 0
    for item in items:
        size = len(json.dumps(formatter(item), ensure_ascii=False))
        if size > max_chars:
            raise AnalysisError(
                "ITEM_TOO_LARGE",
                "Бір мәтін бөлігі тым үлкен; парсерде кіші үзінділерге бөлу қажет.",
            )
        if current and count + size > max_chars:
            yield current
            current, count = [], 0
        current.append(item)
        count += size
    if current:
        yield current
