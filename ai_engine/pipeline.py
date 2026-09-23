"""Public async integration entry point; returns the team's exact v1.0.0 schema."""

import asyncio
import inspect

from .config import Settings
from .errors import AnalysisError
from .extraction import extract
from .matching import comparable, compare_functions, compare_units
from .providers import Provider
from .risks import detect_risks, finding
from .schema import SCHEMA_VERSION, validate
from .sources import SourceRegistry, diagnostic
from .validation import evidence_references, validate_result


class AnalysisEngine:
    """Dependency injection is explicit and intended for tests/adapters, not a
    hidden mock fallback. analyze() always constructs the live provider.
    """

    def __init__(self, settings, provider=None):
        self.settings = settings
        self.provider = provider or Provider(settings)

    async def analyze(self, payload, emit_progress=None):
        registry = SourceRegistry(payload, self.settings.max_input_chars)
        self.settings.require_live()
        warnings = list(registry.warnings)
        callback_failed = False

        async def emit(stage, processed, total, message):
            nonlocal callback_failed
            event = {
                "stage": stage,
                "processed": processed,
                "total": total,
                "message": message,
            }
            validate("ProgressEvent", event, output=True)
            if emit_progress and not callback_failed:
                try:
                    response = emit_progress(event)
                    if not inspect.isawaitable(response):
                        raise TypeError("progress callback must be async")
                    await asyncio.wait_for(response, timeout=5)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    callback_failed = True
                    warnings.append(
                        diagnostic(
                            "PROGRESS_CALLBACK_FAILED",
                            "Прогресс хабарламасын сақтау аяқталмады; талдау жалғасты.",
                        )
                    )

        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                await emit(
                    "extracting",
                    0,
                    None,
                    "Құжаттардан функциялар мен жауаптылар шығарылуда.",
                )
                units, functions, complete, ws = await extract(
                    registry, self.provider, self.settings, emit
                )
                warnings.extend(ws)
                vectors = await self._vectors(functions, warnings)
                await emit(
                    "matching",
                    0,
                    None,
                    "Ұйымдық құрылым және функциялардың өзгерісі салыстырылуда.",
                )
                changes, ws = await compare_units(
                    units, registry, self.provider, self.settings
                )
                organization_complete = not ws
                warnings.extend(ws)
                # Parser completeness alone cannot justify structural absence if
                # entity extraction was incomplete.
                for change in changes:
                    if (
                        change["change_type"] == "removed" and not complete["after"]
                    ) or (
                        change["change_type"] == "created" and not complete["before"]
                    ):
                        change["change_type"], change["basis"] = (
                            "uncertain",
                            "insufficient_data",
                        )
                mappings, ws = await compare_functions(
                    functions,
                    units,
                    registry,
                    self.provider,
                    self.settings,
                    complete,
                    emit,
                    vectors,
                )
                warnings.extend(ws)
                await emit(
                    "verifying", 0, None, "Ауытқулар мен дәлелдер қайта тексерілуде."
                )
                findings, risks_complete, ws = await detect_risks(
                    functions,
                    units,
                    mappings,
                    registry,
                    self.provider,
                    self.settings,
                    complete,
                    emit,
                    vectors,
                )
                warnings.extend(ws)
                for warning in warnings:
                    if warning["code"] == "EMPTY_CLAUSE":
                        findings.append(
                            finding(
                                "document_quality",
                                "Құжаттағы тармақ бос",
                                warning["message"],
                                warning["span_ids"],
                                [],
                                [],
                                payload["analysis_revision"],
                                severity="low",
                                verified=False,
                            )
                        )
                if not any(
                    f["version"] == "before" and comparable(f) for f in functions
                ):
                    complete["before"] = False
                    warnings.append(
                        diagnostic(
                            "NO_BASELINE_FUNCTIONS",
                            "Бұрынғы құжаттардан салыстырылатын функциялар шығарылмады.",
                        )
                    )
                if getattr(self.provider, "cache_hits", 0):
                    warnings.append(
                        diagnostic(
                            "REQUEST_CACHE_USED",
                            f"Осы талдауда қайталанған {self.provider.cache_hits} AI сұрауы кэштен алынды.",
                        )
                    )
                partial = (
                    not all(complete.values())
                    or not risks_complete
                    or not organization_complete
                    or any(m["coverage_status"] == "unknown" for m in mappings)
                )
                result = self._assemble(
                    registry,
                    units,
                    functions,
                    changes,
                    mappings,
                    findings,
                    warnings,
                    partial,
                )
                validate_result(result, registry)
                await emit(
                    result["status"],
                    len(mappings),
                    len(mappings),
                    "Талдау аяқталды."
                    if not partial
                    else "Ішінара нәтиже дайын; шектеулерді қараңыз.",
                )
                # A callback can fail on the final event too.
                if callback_failed and not any(
                    w["code"] == "PROGRESS_CALLBACK_FAILED" for w in result["warnings"]
                ):
                    result["warnings"].append(
                        next(
                            w
                            for w in warnings
                            if w["code"] == "PROGRESS_CALLBACK_FAILED"
                        )
                    )
                return result
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            raise AnalysisError(
                "ANALYSIS_TIMEOUT",
                "Талдауға берілген уақыт аяқталды. Құжат жиынын азайтып немесе уақыт лимитін тексеріп қайта іске қосыңыз.",
                True,
            ) from None

    async def _vectors(self, functions, warnings):
        if not self.settings.nvidia_enabled:
            return None
        vectors = {}
        try:
            for version in ("before", "after"):
                fs = [f for f in functions if f["version"] == version and comparable(f)]
                for i in range(0, len(fs), 16):
                    batch = fs[i : i + 16]
                    texts = [
                        " | ".join(
                            str(f[k] or "")
                            for k in (
                                "action",
                                "object",
                                "scope",
                                "modality",
                                "frequency",
                            )
                        )
                        for f in batch
                    ]
                    values = await self.provider.embeddings(
                        texts, "query" if version == "before" else "passage"
                    )
                    for f, v in zip(batch, values):
                        vectors[f["id"]] = v
            if len({len(x) for x in vectors.values()}) > 1:
                raise AnalysisError(
                    "EMBEDDING_INVALID",
                    "Embedding өлшемдері сұраулар арасында сәйкес емес.",
                )
            return vectors
        except AnalysisError as exc:
            warnings.append(
                diagnostic(
                    "NVIDIA_UNAVAILABLE",
                    "NVIDIA іздеуі қолданылмады. Кейінгі функциялардың толық тізілімі OpenAI арқылы салыстырылады. Себеп коды: "
                    + exc.code,
                )
            )
            return None

    def _assemble(
        self, registry, units, functions, changes, mappings, findings, warnings, partial
    ):
        counts = {k: 0 for k in ("full", "partial", "none", "unknown")}
        mapped_after = set()
        for mapping in mappings:
            counts[mapping["coverage_status"]] += len(mapping["before_function_ids"])
            mapped_after.update(mapping["after_function_ids"])
        coverage = {
            "files_total": len(registry.docs),
            "files_complete": sum(
                d["parse_status"] == "complete" for d in registry.docs.values()
            ),
            "files_partial": sum(
                d["parse_status"] == "partial" for d in registry.docs.values()
            ),
            "files_failed": sum(
                d["parse_status"] == "failed" for d in registry.docs.values()
            ),
            "before_functions_total": sum(counts.values()),
            **counts,
            "after_functions_new": sum(
                f["version"] == "after"
                and comparable(f)
                and f["id"] not in mapped_after
                for f in functions
            ),
            "evidence_links_total": 0,
            "evidence_links_valid": 0,
        }
        # Summary uses templates and validated records: there is no final
        # unconstrained model call that could invent counts or extra conclusions.
        items = []
        for change in changes:
            if change["change_type"] != "preserved":
                items.append(
                    {"text": change["explanation"], "reference_ids": [change["id"]]}
                )
        for item in sorted(
            findings,
            key=lambda f: ({"high": 0, "medium": 1, "low": 2}[f["severity"]], f["id"]),
        ):
            items.append(
                {
                    "text": item["title"] + ": " + item["explanation"],
                    "reference_ids": [item["id"]],
                }
            )
        if not items:
            for mapping in mappings[:5]:
                items.append(
                    {"text": mapping["explanation"], "reference_ids": [mapping["id"]]}
                )
        warnings = list(
            {
                (w["code"], w["message"], w["document_id"], tuple(w["span_ids"])): w
                for w in warnings
            }.values()
        )
        result = {
            "schema_version": SCHEMA_VERSION,
            "analysis_id": registry.payload["analysis_id"],
            "analysis_revision": registry.payload["analysis_revision"],
            "status": "partial" if partial else "completed",
            "documents": registry.summaries(),
            "units": units,
            "unit_changes": changes,
            "functions": functions,
            "mappings": mappings,
            "findings": findings,
            "coverage": coverage,
            "summary": {
                "headline": f"{coverage['before_functions_total']} бұрынғы функция салыстырылды; {counts['unknown']} сәйкестік анықталмаған. Қорытынды жүктелген құжаттарға қатысты және қызметкер тексеруін қажет етеді.",
                "items": items[:15],
            },
            "usage": self.provider.usage(),
            "warnings": warnings,
        }
        total = len(list(evidence_references(result)))
        coverage["evidence_links_total"] = coverage["evidence_links_valid"] = total
        return result


async def analyze(payload: dict, emit_progress=None) -> dict:
    """Backend contract: live analysis only. Missing credentials fail explicitly."""
    settings = Settings.from_env()
    return await AnalysisEngine(settings).analyze(payload, emit_progress)
