import { describe, expect, it } from 'vitest';
import { canRun, fileError, isProcessing, locatorLabel, MAX_FILE_SIZE, owner } from './domain';
import state from '../demo/analysis_state.example.json';
import result from '../demo/analysis_result.example.json';
import source from '../demo/source_evidence.example.json';
import input from '../demo/analysis_input.example.json';
import { validate, ContractError } from '../api/validation';
import type { AnalysisState, AnalysisResult, SourceLocator } from '../api/types';

describe('contract safety', () => {
  it.each([
    ['AnalysisState', state],
    ['AnalysisResult', result],
    ['SourceEvidence', source],
    ['AnalysisInput', input],
  ])('validates %s fixture', (name, data) => {
    expect(validate(name as string, data)).toEqual(data);
  });
  it('rejects unknown fields, wrong counts, invalid enums and absent required data', () => {
    for (const broken of [
      { ...state, schema_version: '2.0.0' },
      { ...state, extra: true },
      { ...state, documents: null },
      { ...state, analysis_revision: -1 },
    ])
      expect(() => validate('AnalysisState', broken)).toThrow(ContractError);
  });
  it('accepts loss mapping without fabricating an after function', () => {
    const data = validate<AnalysisResult>('AnalysisResult', result);
    expect(data.mappings.find((m) => m.coverage_status === 'none')?.after_function_ids).toEqual([]);
    expect(
      data.coverage.full + data.coverage.partial + data.coverage.none + data.coverage.unknown,
    ).toBe(data.coverage.before_functions_total);
  });
});
describe('upload validation', () => {
  it.each(['report.docx', 'report.PDF', 'report.xlsx'])('accepts %s', (name) => {
    expect(fileError({ name, size: MAX_FILE_SIZE })).toBeNull();
  });
  it.each(['bad.doc', 'bad.xls', 'bad.svg', 'report.pdf.exe', 'bad'])('rejects %s', (name) => {
    expect(fileError({ name, size: 10 })).not.toBeNull();
  });
  it('rejects empty and oversized uploads', () => {
    expect(fileError({ name: 'a.pdf', size: 0 })).not.toBeNull();
    expect(fileError({ name: 'a.pdf', size: MAX_FILE_SIZE + 1 })).not.toBeNull();
  });
  it('requires both groups and no running job', () => {
    const s = validate<AnalysisState>('AnalysisState', state);
    expect(canRun(s)).toBe(true);
    expect(canRun(null)).toBe(false);
    expect(canRun({ ...s, status: 'matching' })).toBe(false);
    expect(canRun({ ...s, documents: s.documents.filter((d) => d.version === 'before') })).toBe(
      false,
    );
    expect(
      canRun({ ...s, documents: s.documents.map((d) => ({ ...d, parse_status: 'failed' })) }),
    ).toBe(false);
  });
});
describe('evidence and ownership', () => {
  it('never invents a DOCX page', () => {
    expect(locatorLabel(source.source.locator as SourceLocator)).toBe('2-тармақ');
  });
  it('shows PDF page and XLSX cells', () => {
    expect(locatorLabel({ ...source.source.locator, kind: 'pdf', clause: null, page: 4 })).toBe(
      '4-бет',
    );
    expect(
      locatorLabel({
        ...source.source.locator,
        kind: 'xlsx',
        clause: null,
        sheet: 'Data',
        cell_range: 'A2:B5',
      }),
    ).toBe('Data · A2:B5');
  });
  it('handles nullable owner and processing statuses', () => {
    const r = validate<AnalysisResult>('AnalysisResult', result);
    expect(owner({ ...r.functions[0], unit_id: null, role_id: null }, r.units)).toBe(
      'Жауапты анықталмаған',
    );
    expect(isProcessing('verifying')).toBe(true);
    expect(isProcessing('failed')).toBe(false);
  });
});
