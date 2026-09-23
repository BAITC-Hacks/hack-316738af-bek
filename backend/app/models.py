"""Generated from contracts/openapi.json; regenerate with backend/scripts/generate_models.py."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Diagnostic(ContractModel):
    code: str
    message: str
    document_id: str | None
    span_ids: list[str]


class SourceLocator(ContractModel):
    kind: Literal["docx", "pdf", "xlsx"]
    clause: str | None
    path: str
    page: Annotated[int, Field(ge=1)] | None
    sheet: str | None
    cell_range: str | None


class SourceSpan(ContractModel):
    id: str
    document_id: str
    raw_text: str
    section_path: list[str]
    context_span_ids: list[str]
    locator: SourceLocator
    is_content: bool


class DocumentSummary(ContractModel):
    id: str
    version: Literal["before", "after"]
    filename: str
    title: str
    document_type: Literal["regulation", "order", "job_description", "structure", "appendix", "other", "unknown"]
    edition: str | None
    source_sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
    parse_status: Literal["pending", "complete", "partial", "failed"]
    span_count: Annotated[int, Field(ge=0)]
    warnings: list[Diagnostic]


class ParsedDocument(ContractModel):
    id: str
    version: Literal["before", "after"]
    filename: str
    title: str
    document_type: Literal["regulation", "order", "job_description", "structure", "appendix", "other", "unknown"]
    edition: str | None
    source_sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
    parse_status: Literal["pending", "complete", "partial", "failed"]
    span_count: Annotated[int, Field(ge=0)]
    warnings: list[Diagnostic]
    spans: list[SourceSpan]


class AnalysisInput(ContractModel):
    schema_version: Literal["1.0.0"]
    analysis_id: str
    analysis_revision: Annotated[int, Field(ge=1)]
    documents: list[ParsedDocument]


class Unit(ContractModel):
    id: str
    version: Literal["before", "after"]
    name: str
    aliases: list[str]
    kind: Literal["organization", "department", "role", "unknown"]
    parent_id: str | None
    source_span_ids: list[str]


class UnitChange(ContractModel):
    id: str
    before_unit_ids: list[str]
    after_unit_ids: list[str]
    change_type: Literal[
        "preserved", "created", "removed", "renamed", "merged", "split", "reorganized", "reporting_changed", "uncertain"
    ]
    basis: Literal["explicit_document", "inferred_functional_match", "insufficient_data"]
    explanation: str
    source_span_ids: list[str]


class Function(ContractModel):
    id: str
    version: Literal["before", "after"]
    unit_id: str | None
    role_id: str | None
    action: str
    object: str
    scope: str | None
    modality: Literal["obligation", "permission", "prohibition", "definition"]
    conditions: list[str]
    frequency: str | None
    deliverable: str | None
    recipient: str | None
    source_span_ids: list[str]
    context_span_ids: list[str]


class FunctionMapping(ContractModel):
    id: str
    before_function_ids: list[str]
    after_function_ids: list[str]
    coverage_status: Literal["full", "partial", "none", "unknown"]
    change_flags: list[
        Literal[
            "transferred",
            "renamed",
            "split",
            "merged",
            "wording_changed",
            "scope_changed",
            "frequency_changed",
            "authority_changed",
        ]
    ]
    uncovered_aspects: list[str]
    explanation: str
    source_span_ids: list[str]
    context_evidence_ids: list[str]


class RecommendedAction(ContractModel):
    action: str
    target_role_id: str | None
    required_document: str | None
    reason: str


class Finding(ContractModel):
    id: str
    analysis_revision: Annotated[int, Field(ge=1)]
    type: Literal["potential_loss", "ownership_gap", "potential_duplicate", "potential_conflict", "document_quality"]
    risk_change: Literal["new", "persisting", "no_longer_detected", "changed", "unknown"]
    title: str
    explanation: str
    severity: Literal["low", "medium", "high"]
    evidence_ids: list[str]
    context_evidence_ids: list[str]
    counterevidence_ids: list[str]
    affected_units: list[str]
    recommended_action: RecommendedAction
    verification_status: Literal["validated", "needs_review", "incomplete"]
    review_status: Literal["unreviewed", "confirmed", "rejected", "needs_information"]
    search_scope_document_ids: list[str]
    search_complete: bool


class Coverage(ContractModel):
    files_total: Annotated[int, Field(ge=0)]
    files_complete: Annotated[int, Field(ge=0)]
    files_partial: Annotated[int, Field(ge=0)]
    files_failed: Annotated[int, Field(ge=0)]
    before_functions_total: Annotated[int, Field(ge=0)]
    full: Annotated[int, Field(ge=0)]
    partial: Annotated[int, Field(ge=0)]
    none: Annotated[int, Field(ge=0)]
    unknown: Annotated[int, Field(ge=0)]
    after_functions_new: Annotated[int, Field(ge=0)]
    evidence_links_total: Annotated[int, Field(ge=0)]
    evidence_links_valid: Annotated[int, Field(ge=0)]


class SummaryItem(ContractModel):
    text: str
    reference_ids: list[str]


class Summary(ContractModel):
    headline: str
    items: list[SummaryItem]


class Usage(ContractModel):
    provider: str
    model: str
    input_tokens: Annotated[int, Field(ge=0)] | None
    output_tokens: Annotated[int, Field(ge=0)] | None
    calls: Annotated[int, Field(ge=0)]
    elapsed_ms: Annotated[int, Field(ge=0)]


class AnalysisResult(ContractModel):
    schema_version: Literal["1.0.0"]
    analysis_id: str
    analysis_revision: Annotated[int, Field(ge=1)]
    status: Literal["completed", "partial"]
    documents: list[DocumentSummary]
    units: list[Unit]
    unit_changes: list[UnitChange]
    functions: list[Function]
    mappings: list[FunctionMapping]
    findings: list[Finding]
    coverage: Coverage
    summary: Summary
    usage: list[Usage]
    warnings: list[Diagnostic]


class ProgressEvent(ContractModel):
    stage: Literal["uploaded", "parsing", "extracting", "matching", "verifying", "completed", "partial", "failed"]
    processed: Annotated[int, Field(ge=0)]
    total: Annotated[int, Field(ge=0)] | None
    message: str


class AnalysisState(ContractModel):
    schema_version: Literal["1.0.0"]
    analysis_id: str
    analysis_revision: Annotated[int, Field(ge=1)]
    status: Literal["uploaded", "parsing", "extracting", "matching", "verifying", "completed", "partial", "failed"]
    documents: list[DocumentSummary]
    progress: ProgressEvent
    warnings: list[Diagnostic]


class SourceEvidence(ContractModel):
    document: DocumentSummary
    source: SourceSpan
    context: list[SourceSpan]


class ReviewPatch(ContractModel):
    analysis_revision: Annotated[int, Field(ge=1)]
    review_status: Literal["unreviewed", "confirmed", "rejected", "needs_information"]
    note: str


class FindingReview(ContractModel):
    finding_id: str
    analysis_revision: Annotated[int, Field(ge=1)]
    review_status: Literal["unreviewed", "confirmed", "rejected", "needs_information"]
    note: str
    reviewed_at: str


class DocumentPatch(ContractModel):
    expected_revision: Annotated[int, Field(ge=1)]
    version: Literal["before", "after"]


class RunRequest(ContractModel):
    expected_revision: Annotated[int, Field(ge=1)]


class Error(ContractModel):
    code: str
    message: str
    retryable: bool


class Health(ContractModel):
    status: Literal["ok"]
    schema_version: Literal["1.0.0"]
    openai_configured: bool
    nvidia_configured: bool


Diagnostic.model_rebuild()

SourceLocator.model_rebuild()

SourceSpan.model_rebuild()

DocumentSummary.model_rebuild()

ParsedDocument.model_rebuild()

AnalysisInput.model_rebuild()

Unit.model_rebuild()

UnitChange.model_rebuild()

Function.model_rebuild()

FunctionMapping.model_rebuild()

RecommendedAction.model_rebuild()

Finding.model_rebuild()

Coverage.model_rebuild()

SummaryItem.model_rebuild()

Summary.model_rebuild()

Usage.model_rebuild()

AnalysisResult.model_rebuild()

ProgressEvent.model_rebuild()

AnalysisState.model_rebuild()

SourceEvidence.model_rebuild()

ReviewPatch.model_rebuild()

FindingReview.model_rebuild()

DocumentPatch.model_rebuild()

RunRequest.model_rebuild()

Error.model_rebuild()

Health.model_rebuild()
