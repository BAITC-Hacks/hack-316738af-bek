import type { AnalysisState, Function as OrgFunction, SourceLocator, Unit } from '../api/types';

export const MAX_FILE_SIZE = 20 * 1024 * 1024;
export const MAX_FILES = 10;
export function fileError(file: Pick<File, 'name' | 'size'>): string | null {
  if (!/\.(docx|pdf|xlsx)$/i.test(file.name))
    return 'Тек DOCX, PDF немесе XLSX файлдарын таңдаңыз. DOC және XLS файлдарын алдымен түрлендіріңіз.';
  if (file.size === 0) return 'Файл бос. Мәтіні бар құжатты таңдаңыз.';
  if (file.size > MAX_FILE_SIZE) return 'Файл көлемі 20 МБ-тан аспауы керек.';
  return null;
}
export const isProcessing = (status?: string) =>
  ['parsing', 'extracting', 'matching', 'verifying'].includes(status ?? '');
export const isReady = (status?: string) => status === 'completed' || status === 'partial';
export function canRun(state: AnalysisState | null) {
  return (
    !!state &&
    !isProcessing(state.status) &&
    (['before', 'after'] as const).every((v) =>
      state.documents.some((d) => d.version === v && d.parse_status !== 'failed'),
    )
  );
}
export function locatorLabel(l: SourceLocator) {
  return (
    [
      l.clause && `${l.clause}-тармақ`,
      l.page != null && `${l.page}-бет`,
      l.sheet && `${l.sheet}${l.cell_range ? ` · ${l.cell_range}` : ''}`,
    ]
      .filter(Boolean)
      .join(' · ') || l.path
  );
}
export function owner(f: OrgFunction, units: Unit[]) {
  return (
    [f.unit_id, f.role_id]
      .filter((id, i, ids) => id && ids.indexOf(id) === i)
      .map((id) => units.find((u) => u.id === id)?.name ?? 'Жауапты анықталмаған')
      .join(' / ') || 'Жауапты анықталмаған'
  );
}
export const functionText = (f: OrgFunction) => `${f.object} · ${f.action}`;
export const labels: Record<string, string> = {
  before: 'Дейін',
  after: 'Кейін',
  uploaded: 'Құжаттар жүктелді',
  parsing: 'Құжаттар оқылуда',
  extracting: 'Функциялар анықталуда',
  matching: 'Сәйкестіктер ізделуде',
  verifying: 'Дәлелдер тексерілуде',
  completed: 'Талдау аяқталды',
  partial: 'Ішінара',
  failed: 'Қате',
  pending: 'Кезекте',
  complete: 'Толық оқылды',
  full: 'Толық сақталған',
  none: 'Кейін табылмады',
  unknown: 'Дерек жеткіліксіз',
  potential_loss: 'Ықтимал жоғалу',
  ownership_gap: 'Жауапты белгісіз',
  potential_duplicate: 'Ықтимал қайталану',
  potential_conflict: 'Ықтимал қақтығыс',
  document_quality: 'Құжат сапасы',
  new: 'Жаңа',
  persisting: 'Бұрыннан бар',
  no_longer_detected: 'Енді анықталмады',
  changed: 'Өзгерген',
  unreviewed: 'Қаралмаған',
  confirmed: 'Расталды',
  rejected: 'Қабылданбады',
  needs_information: 'Ақпарат қажет',
  validated: 'Дәлелдер тексерілді',
  needs_review: 'Тексеру қажет',
  incomplete: 'Тексеру толық емес',
  low: 'Төмен',
  medium: 'Орташа',
  high: 'Жоғары',
  preserved: 'Сақталған',
  created: 'Жаңадан көрсетілген',
  removed: 'Кейін кездеспейді',
  renamed: 'Атауы өзгерген',
  merged: 'Біріккен',
  split: 'Бөлінген',
  reorganized: 'Қайта ұйымдастырылған',
  reporting_changed: 'Бағыныштылығы өзгерген',
  uncertain: 'Нақтылау қажет',
  explicit_document: 'Құжаттағы нақты дерек',
  inferred_functional_match: 'Функциялардан алынған болжам',
  insufficient_data: 'Дерек жеткіліксіз',
  transferred: 'Жауаптысы ауысқан',
  wording_changed: 'Мәтіні өзгерген',
  scope_changed: 'Ауқымы өзгерген',
  frequency_changed: 'Жиілігі өзгерген',
  authority_changed: 'Өкілеттігі өзгерген',
  regulation: 'Ереже',
  order: 'Өкім',
  job_description: 'Лауазымдық нұсқаулық',
  structure: 'Құрылым',
  appendix: 'Қосымша',
  other: 'Басқа',
  obligation: 'Міндет',
  permission: 'Құқық',
  prohibition: 'Тыйым',
  definition: 'Анықтама',
};
export const label = (key: string) => labels[key] ?? key;
export function safeRead(key: string) {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}
export function safeWrite(key: string, value: string | null) {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, value);
  } catch {
    /* Private browsing can disable storage; in-memory state still works. */
  }
}
