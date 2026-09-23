// Generated from contracts/openapi.json. Do not edit. SHA256: b8b529d5e9840dcdcda42d91df6359e4584ddea84cdedea17020d7a55dfc8fe9
export type Diagnostic = {
  code: string;
  message: string;
  document_id: string | null;
  span_ids: Array<string>;
};

export type SourceLocator = {
  kind: "docx" | "pdf" | "xlsx";
  clause: string | null;
  path: string;
  page: number | null;
  sheet: string | null;
  cell_range: string | null;
};

export type SourceSpan = {
  id: string;
  document_id: string;
  raw_text: string;
  section_path: Array<string>;
  context_span_ids: Array<string>;
  locator: SourceLocator;
  is_content: boolean;
};

export type DocumentSummary = {
  id: string;
  version: "before" | "after";
  filename: string;
  title: string;
  document_type: "regulation" | "order" | "job_description" | "structure" | "appendix" | "other" | "unknown";
  edition: string | null;
  source_sha256: string;
  parse_status: "pending" | "complete" | "partial" | "failed";
  span_count: number;
  warnings: Array<Diagnostic>;
};

export type ParsedDocument = {
  id: string;
  version: "before" | "after";
  filename: string;
  title: string;
  document_type: "regulation" | "order" | "job_description" | "structure" | "appendix" | "other" | "unknown";
  edition: string | null;
  source_sha256: string;
  parse_status: "pending" | "complete" | "partial" | "failed";
  span_count: number;
  warnings: Array<Diagnostic>;
  spans: Array<SourceSpan>;
};

export type AnalysisInput = {
  schema_version: "1.0.0";
  analysis_id: string;
  analysis_revision: number;
  documents: Array<ParsedDocument>;
};

export type Unit = {
  id: string;
  version: "before" | "after";
  name: string;
  aliases: Array<string>;
  kind: "organization" | "department" | "role" | "unknown";
  parent_id: string | null;
  source_span_ids: Array<string>;
};

export type UnitChange = {
  id: string;
  before_unit_ids: Array<string>;
  after_unit_ids: Array<string>;
  change_type: "preserved" | "created" | "removed" | "renamed" | "merged" | "split" | "reorganized" | "reporting_changed" | "uncertain";
  basis: "explicit_document" | "inferred_functional_match" | "insufficient_data";
  explanation: string;
  source_span_ids: Array<string>;
};

export type Function = {
  id: string;
  version: "before" | "after";
  unit_id: string | null;
  role_id: string | null;
  action: string;
  object: string;
  scope: string | null;
  modality: "obligation" | "permission" | "prohibition" | "definition";
  conditions: Array<string>;
  frequency: string | null;
  deliverable: string | null;
  recipient: string | null;
  source_span_ids: Array<string>;
  context_span_ids: Array<string>;
};

export type FunctionMapping = {
  id: string;
  before_function_ids: Array<string>;
  after_function_ids: Array<string>;
  coverage_status: "full" | "partial" | "none" | "unknown";
  change_flags: Array<"transferred" | "renamed" | "split" | "merged" | "wording_changed" | "scope_changed" | "frequency_changed" | "authority_changed">;
  uncovered_aspects: Array<string>;
  explanation: string;
  source_span_ids: Array<string>;
  context_evidence_ids: Array<string>;
};

export type RecommendedAction = {
  action: string;
  target_role_id: string | null;
  required_document: string | null;
  reason: string;
};

export type Finding = {
  id: string;
  analysis_revision: number;
  type: "potential_loss" | "ownership_gap" | "potential_duplicate" | "potential_conflict" | "document_quality";
  risk_change: "new" | "persisting" | "no_longer_detected" | "changed" | "unknown";
  title: string;
  explanation: string;
  severity: "low" | "medium" | "high";
  evidence_ids: Array<string>;
  context_evidence_ids: Array<string>;
  counterevidence_ids: Array<string>;
  affected_units: Array<string>;
  recommended_action: RecommendedAction;
  verification_status: "validated" | "needs_review" | "incomplete";
  review_status: "unreviewed" | "confirmed" | "rejected" | "needs_information";
  search_scope_document_ids: Array<string>;
  search_complete: boolean;
};

export type Coverage = {
  files_total: number;
  files_complete: number;
  files_partial: number;
  files_failed: number;
  before_functions_total: number;
  full: number;
  partial: number;
  none: number;
  unknown: number;
  after_functions_new: number;
  evidence_links_total: number;
  evidence_links_valid: number;
};

export type SummaryItem = {
  text: string;
  reference_ids: Array<string>;
};

export type Summary = {
  headline: string;
  items: Array<SummaryItem>;
};

export type Usage = {
  provider: string;
  model: string;
  input_tokens: number | null;
  output_tokens: number | null;
  calls: number;
  elapsed_ms: number;
};

export type AnalysisResult = {
  schema_version: "1.0.0";
  analysis_id: string;
  analysis_revision: number;
  status: "completed" | "partial";
  documents: Array<DocumentSummary>;
  units: Array<Unit>;
  unit_changes: Array<UnitChange>;
  functions: Array<Function>;
  mappings: Array<FunctionMapping>;
  findings: Array<Finding>;
  coverage: Coverage;
  summary: Summary;
  usage: Array<Usage>;
  warnings: Array<Diagnostic>;
};

export type ProgressEvent = {
  stage: "uploaded" | "parsing" | "extracting" | "matching" | "verifying" | "completed" | "partial" | "failed";
  processed: number;
  total: number | null;
  message: string;
};

export type AnalysisState = {
  schema_version: "1.0.0";
  analysis_id: string;
  analysis_revision: number;
  status: "uploaded" | "parsing" | "extracting" | "matching" | "verifying" | "completed" | "partial" | "failed";
  documents: Array<DocumentSummary>;
  progress: ProgressEvent;
  warnings: Array<Diagnostic>;
};

export type SourceEvidence = {
  document: DocumentSummary;
  source: SourceSpan;
  context: Array<SourceSpan>;
};

export type ReviewPatch = {
  analysis_revision: number;
  review_status: "unreviewed" | "confirmed" | "rejected" | "needs_information";
  note: string;
};

export type FindingReview = {
  finding_id: string;
  analysis_revision: number;
  review_status: "unreviewed" | "confirmed" | "rejected" | "needs_information";
  note: string;
  reviewed_at: string;
};

export type DocumentPatch = {
  expected_revision: number;
  version: "before" | "after";
};

export type RunRequest = {
  expected_revision: number;
};

export type Error = {
  code: string;
  message: string;
  retryable: boolean;
};

export type Health = {
  status: "ok";
  schema_version: "1.0.0";
  openai_configured: boolean;
  nvidia_configured: boolean;
};
