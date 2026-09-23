import { useMemo, useState } from 'react';
import {
  ArrowRight,
  CheckCheck,
  ChevronRight,
  Download,
  FileCheck2,
  FileText,
  GitBranch,
  ListFilter,
  Search,
  ShieldAlert,
  SlidersHorizontal,
} from 'lucide-react';
import type {
  AnalysisResult,
  Finding,
  FindingReview,
  Function as OrgFunction,
  FunctionMapping,
  ReviewPatch,
} from '../api/types';
import { functionText, label, owner } from '../lib/domain';
import { Alert, Badge, Empty, EvidenceLinks } from './common';

export type ResultTab = 'risks' | 'functions' | 'structure';
type EvidenceOpen = (ids: string[], title: string) => void;
type ReviewSave = (id: string, patch: ReviewPatch) => Promise<FindingReview | undefined>;
type Props = {
  result: AnalysisResult;
  tab: ResultTab;
  setTab: (tab: ResultTab) => void;
  onEvidence: EvidenceOpen;
  review: ReviewSave;
  reviews: Record<string, FindingReview>;
  busy: boolean;
  onExport: () => void;
};

function SelectFilter({
  title,
  value,
  setValue,
  options,
}: {
  title: string;
  value: string;
  setValue: (s: string) => void;
  options: { value: string; title: string }[];
}) {
  return (
    <label className="filter">
      <span>{title}</span>
      <select aria-label={title} value={value} onChange={(e) => setValue(e.target.value)}>
        <option value="">Барлығы</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.title}
          </option>
        ))}
      </select>
    </label>
  );
}
const options = (keys: string[]) => keys.map((value) => ({ value, title: label(value) }));
function SearchInput({
  value,
  setValue,
  placeholder,
}: {
  value: string;
  setValue: (s: string) => void;
  placeholder: string;
}) {
  return (
    <label className="search">
      <Search size={17} />
      <input
        type="search"
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
    </label>
  );
}

function FindingDetail({
  finding: f,
  result,
  onEvidence,
  review,
  saved,
  busy,
}: {
  finding: Finding;
  result: AnalysisResult;
  onEvidence: EvidenceOpen;
  review: ReviewSave;
  saved?: FindingReview;
  busy: boolean;
}) {
  const [status, setStatus] = useState(f.review_status);
  const [note, setNote] = useState(saved?.note ?? '');
  const [savedMessage, setSavedMessage] = useState('');
  async function submit() {
    setSavedMessage('');
    const response = await review(f.id, {
      analysis_revision: result.analysis_revision,
      review_status: status,
      note,
    });
    if (response) setSavedMessage('Шешім мен түсініктеме сақталды.');
  }
  return (
    <aside className="finding-detail" aria-label="Тәуекелді тексеру">
      <div className="detail-heading">
        <span className="eyebrow">ЖАҒДАЙДЫ ТЕКСЕРУ</span>
        <Badge value={f.severity}>{label(f.severity)} әсер</Badge>
      </div>
      <h3>{f.title}</h3>
      <p>{f.explanation}</p>
      <div className="detail-badges">
        <Badge value={f.type} />
        <Badge value={f.risk_change} />
      </div>
      <div className="detail-section">
        <h4>Дәлелдер тізбегі</h4>
        <EvidenceLinks ids={f.evidence_ids} onOpen={onEvidence} title="Қолдайтын дәлел" />
        {f.context_evidence_ids.length > 0 && (
          <EvidenceLinks ids={f.context_evidence_ids} onOpen={onEvidence} title="Контекст" />
        )}
        <div className="counter-evidence">
          <span>Қарсы дәлел</span>
          {f.counterevidence_ids.length ? (
            <EvidenceLinks
              ids={f.counterevidence_ids}
              onOpen={onEvidence}
              title="Қарсы дәлелді ашу"
            />
          ) : (
            <small>Тіркелмеген</small>
          )}
        </div>
        <Badge value={f.verification_status} />
        <p className="small muted">
          Дәлелді тексеру мәртебесі қызметкердің растауын алмастырмайды.
        </p>
      </div>
      {(f.search_scope_document_ids.length > 0 ||
        f.type === 'potential_loss' ||
        f.risk_change === 'no_longer_detected') && (
        <div className="detail-section">
          <h4>Іздеу ауқымы</h4>
          <p className="small">
            {f.search_complete
              ? 'Көрсетілген құжаттар бойынша іздеу аяқталған.'
              : 'Іздеу толық аяқталмаған. Қосымша дерек қажет.'}
          </p>
          <ul className="scope-list">
            {f.search_scope_document_ids.map((id) => (
              <li key={id}>
                <FileText size={14} />
                {result.documents.find((d) => d.id === id)?.filename ?? 'Құжат атауы берілмеген'}
              </li>
            ))}
          </ul>
          <p className="small muted">Бұл ұйымның барлық құжаты ұсынылғанын білдірмейді.</p>
        </div>
      )}
      <div className="recommendation">
        <span>
          <CheckCheck size={17} />
          Ұсынылатын әрекет
        </span>
        <p>{f.recommended_action.action}</p>
        <small>{f.recommended_action.reason}</small>
        {f.recommended_action.required_document && (
          <p className="small">
            <b>Сұралатын құжат:</b> {f.recommended_action.required_document}
          </p>
        )}
        <p className="small">
          <b>Жауапты:</b>{' '}
          {result.units.find((u) => u.id === f.recommended_action.target_role_id)?.name ??
            'Деректе нақтыланбаған'}
        </p>
      </div>
      <form
        className="review-form"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <h4>Сіздің шешіміңіз</h4>
        <label>
          Тексеру күйі
          <select
            aria-label="Тексеру күйі"
            value={status}
            disabled={busy}
            onChange={(e) => {
              setStatus(e.target.value as Finding['review_status']);
              setSavedMessage('');
            }}
          >
            {options(['unreviewed', 'confirmed', 'rejected', 'needs_information']).map((o) => (
              <option key={o.value} value={o.value}>
                {o.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Түсініктеме
          <textarea
            rows={3}
            maxLength={5000}
            value={note}
            disabled={busy}
            onChange={(e) => {
              setNote(e.target.value);
              setSavedMessage('');
            }}
            placeholder="Шешімнің негізін немесе қажет ақпаратты жазыңыз…"
          />
        </label>
        {f.review_status !== 'unreviewed' && !saved && (
          <p className="small muted">
            Бұрынғы түсініктеме API-дан оқылмайды. Сақтау түсініктемені осы мәтінмен алмастырады;
            бұрынғы жазбаны есептен көріңіз.
          </p>
        )}
        <button className="button primary" disabled={busy} type="submit">
          <CheckCheck size={16} />
          {busy ? 'Сақталуда…' : 'Шешімді сақтау'}
        </button>
        {savedMessage && (
          <p className="saved-message" role="status">
            {savedMessage}
          </p>
        )}
      </form>
    </aside>
  );
}
function Risks({
  result,
  onEvidence,
  review,
  reviews,
  busy,
}: Pick<Props, 'result' | 'onEvidence' | 'review' | 'reviews' | 'busy'>) {
  const [query, setQuery] = useState('');
  const [type, setType] = useState('');
  const [change, setChange] = useState('');
  const [unit, setUnit] = useState('');
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState(result.findings[0]?.id ?? '');
  const filtered = result.findings.filter(
    (f) =>
      (!type || f.type === type) &&
      (!change || f.risk_change === change) &&
      (!unit || f.affected_units.includes(unit)) &&
      (!status || f.review_status === status) &&
      `${f.title} ${f.explanation}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
  );
  const current = result.findings.find((f) => f.id === selected);
  const clear = () => {
    setQuery('');
    setType('');
    setChange('');
    setUnit('');
    setStatus('');
  };
  return (
    <>
      <div className="table-tools">
        <SearchInput value={query} setValue={setQuery} placeholder="Тәуекелді іздеу…" />
        <span className="muted small">
          <ListFilter size={15} />
          {filtered.length} / {result.findings.length} жағдай
        </span>
      </div>
      <div className="filters">
        <SlidersHorizontal size={17} className="filter-icon" />
        <SelectFilter
          title="Түрі"
          value={type}
          setValue={setType}
          options={options([
            'potential_loss',
            'ownership_gap',
            'potential_duplicate',
            'potential_conflict',
            'document_quality',
          ])}
        />
        <SelectFilter
          title="Өзгерісі"
          value={change}
          setValue={setChange}
          options={options(['new', 'persisting', 'no_longer_detected', 'changed', 'unknown'])}
        />
        <SelectFilter
          title="Бөлімше"
          value={unit}
          setValue={setUnit}
          options={result.units.map((u) => ({
            value: u.id,
            title: `${u.name} · ${label(u.version)}`,
          }))}
        />
        <SelectFilter
          title="Шешім"
          value={status}
          setValue={setStatus}
          options={options(['unreviewed', 'confirmed', 'rejected', 'needs_information'])}
        />
        {(query || type || change || unit || status) && (
          <button className="text-button" onClick={clear}>
            Тазалау
          </button>
        )}
      </div>
      <div className={`risk-layout ${!current ? 'no-selection' : ''}`}>
        <div className="risk-list">
          {filtered.length ? (
            filtered.map((f, i) => (
              <button
                key={f.id}
                className={`risk-row ${selected === f.id ? 'selected' : ''}`}
                onClick={() => setSelected(f.id)}
                aria-pressed={selected === f.id}
              >
                <span className={`risk-level ${f.severity}`}>
                  <ShieldAlert size={20} />
                </span>
                <div className="risk-content">
                  <div className="risk-kicker">
                    <span>ЖАҒДАЙ {String(i + 1).padStart(2, '0')}</span>
                    <Badge value={f.risk_change} />
                  </div>
                  <h3>{f.title}</h3>
                  <p>
                    {[
                      ...new Set(
                        f.affected_units.map(
                          (id) => result.units.find((u) => u.id === id)?.name ?? 'Белгісіз бөлімше',
                        ),
                      ),
                    ].join(' · ')}
                  </p>
                  <div className="risk-row-bottom">
                    <span>{label(f.type)}</span>
                    <Badge value={f.review_status} />
                  </div>
                </div>
                <ChevronRight size={17} className="row-chevron" />
              </button>
            ))
          ) : (
            <Empty
              title={result.findings.length ? 'Сүзгіге сай жағдай жоқ' : 'Тәуекелдер тізімі бос'}
              text={
                result.findings.length
                  ? 'Сүзгілерді өзгертіңіз немесе іздеуді тазалаңыз.'
                  : 'Бұл нәтиже тәуекел тіркемеген. Қамту мен диагностиканы да қарап шығыңыз.'
              }
            >
              {result.findings.length > 0 && (
                <button className="button secondary" onClick={clear}>
                  Сүзгілерді тазалау
                </button>
              )}
            </Empty>
          )}
        </div>
        {current && (
          <FindingDetail
            key={`${current.id}:${result.analysis_revision}`}
            finding={current}
            result={result}
            onEvidence={onEvidence}
            review={review}
            saved={reviews[current.id]}
            busy={busy}
          />
        )}
      </div>
    </>
  );
}

function FunctionCell({
  functions,
  result,
  onEvidence,
}: {
  functions: OrgFunction[];
  result: AnalysisResult;
  onEvidence: EvidenceOpen;
}) {
  if (!functions.length) return <p className="missing-value">Кейінгі жиында сәйкестік жоқ</p>;
  return (
    <>
      {functions.map((f) => (
        <div key={f.id} className="function-cell">
          <strong>{functionText(f)}</strong>
          <span>{owner(f, result.units)}</span>
          <small>{[label(f.modality), f.frequency, f.scope].filter(Boolean).join(' · ')}</small>
          {f.conditions.length > 0 && <p className="small">Шарттар: {f.conditions.join('; ')}</p>}
          {(f.deliverable || f.recipient) && (
            <p className="small">
              {[f.deliverable && `Нәтиже: ${f.deliverable}`, f.recipient && `Алушы: ${f.recipient}`]
                .filter(Boolean)
                .join(' · ')}
            </p>
          )}
          <EvidenceLinks
            ids={[...f.source_span_ids, ...f.context_span_ids]}
            onOpen={onEvidence}
            title="Мәтін және контекст"
          />
        </div>
      ))}
    </>
  );
}
function Functions({ result, onEvidence }: Pick<Props, 'result' | 'onEvidence'>) {
  const [query, setQuery] = useState('');
  const [coverage, setCoverage] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const get = (ids: string[]) => result.functions.filter((f) => ids.includes(f.id));
  const mappings = result.mappings.filter(
    (m) =>
      (!coverage || m.coverage_status === coverage) &&
      [
        m.explanation,
        ...get([...m.before_function_ids, ...m.after_function_ids]).map(
          (f) => `${functionText(f)} ${owner(f, result.units)}`,
        ),
      ]
        .join(' ')
        .toLocaleLowerCase()
        .includes(query.toLocaleLowerCase()),
  );
  const mappedAfter = new Set(result.mappings.flatMap((m) => m.after_function_ids));
  const newFunctions = result.functions.filter(
    (f) =>
      f.version === 'after' &&
      ['obligation', 'permission'].includes(f.modality) &&
      !mappedAfter.has(f.id),
  );
  return (
    <>
      <div className="table-tools">
        <SearchInput
          value={query}
          setValue={setQuery}
          placeholder="Функция немесе жауаптыны іздеу…"
        />
        <SelectFilter
          title="Қамту"
          value={coverage}
          setValue={setCoverage}
          options={options(['full', 'partial', 'none', 'unknown'])}
        />
      </div>
      {mappings.length ? (
        <div
          className="table-scroll"
          tabIndex={0}
          role="region"
          aria-label="Функцияларды салыстыру кестесі"
        >
          <table className="function-table">
            <thead>
              <tr>
                <th>Дейін · міндет пен жауапты</th>
                <th>Кейін · міндет пен жауапты</th>
                <th>Қамту және өзгерістер</th>
              </tr>
            </thead>
            <tbody>
              {mappings.map((m) => (
                <FunctionRow
                  key={m.id}
                  mapping={m}
                  before={get(m.before_function_ids)}
                  after={get(m.after_function_ids)}
                  result={result}
                  onEvidence={onEvidence}
                  expanded={expanded === m.id}
                  toggle={() => setExpanded(expanded === m.id ? null : m.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          title="Сәйкестік көрсетілмеген"
          text="Іздеу мен қамту сүзгісін тексеріңіз. Бос нәтиже міндеттердің сақталғанын білдірмейді."
        />
      )}
      {newFunctions.length > 0 && (
        <section className="new-functions">
          <h3>
            Кейінгі жаңа функциялар{' '}
            <span className="count">{result.coverage.after_functions_new}</span>
          </h3>
          <div className="new-functions-grid">
            {newFunctions.map((f) => (
              <div key={f.id}>
                <Badge value="new" />
                <FunctionCell functions={[f]} result={result} onEvidence={onEvidence} />
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
function FunctionRow({
  mapping: m,
  before,
  after,
  result,
  onEvidence,
  expanded,
  toggle,
}: {
  mapping: FunctionMapping;
  before: OrgFunction[];
  after: OrgFunction[];
  result: AnalysisResult;
  onEvidence: EvidenceOpen;
  expanded: boolean;
  toggle: () => void;
}) {
  return (
    <>
      <tr>
        <td>
          <FunctionCell functions={before} result={result} onEvidence={onEvidence} />
        </td>
        <td>
          <FunctionCell functions={after} result={result} onEvidence={onEvidence} />
        </td>
        <td>
          <Badge value={m.coverage_status} />
          <div className="change-flags">
            {m.change_flags.map((flag) => (
              <Badge key={flag} value={flag} />
            ))}
          </div>
          <button className="text-button" aria-expanded={expanded} onClick={toggle}>
            Негіздеме <ChevronRight size={15} />
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="mapping-explanation">
          <td colSpan={3}>
            <div className="function-path">
              <span>{before.map((f) => owner(f, result.units)).join(', ') || 'Белгісіз'}</span>
              <ArrowRight size={17} />
              <span>
                {after.map((f) => owner(f, result.units)).join(', ') || 'Сәйкестік табылмады'}
              </span>
            </div>
            <p>{m.explanation}</p>
            {m.uncovered_aspects.length > 0 && (
              <p>
                <b>Қамтылмаған:</b> {m.uncovered_aspects.join('; ')}
              </p>
            )}
            <EvidenceLinks
              ids={[...m.source_span_ids, ...m.context_evidence_ids]}
              onOpen={onEvidence}
              title="Сәйкестік дәлелдері"
            />
          </td>
        </tr>
      )}
    </>
  );
}
function Structure({ result, onEvidence }: Pick<Props, 'result' | 'onEvidence'>) {
  return (
    <div className="structure">
      <div className="structure-columns">
        {(['before', 'after'] as const).map((v) => (
          <section key={v}>
            <div className="structure-column-head">
              <span className="version-marker">{v === 'before' ? 'A' : 'B'}</span>
              <h3>{label(v)}</h3>
              <span className="count">{result.units.filter((u) => u.version === v).length}</span>
            </div>
            {result.units
              .filter((u) => u.version === v)
              .map((u) => (
                <article key={u.id} className={`unit-card ${u.parent_id ? 'child' : ''}`}>
                  <GitBranch size={20} />
                  <div>
                    <h4>{u.name}</h4>
                    {u.parent_id && (
                      <p>
                        Бағынады:{' '}
                        {result.units.find((p) => p.id === u.parent_id)?.name ??
                          'Атауы көрсетілмеген'}
                      </p>
                    )}
                    {u.aliases.length > 0 && <p>{u.aliases.join(', ')}</p>}
                    <EvidenceLinks ids={u.source_span_ids} onOpen={onEvidence} />
                  </div>
                </article>
              ))}
            {!result.units.some((u) => u.version === v) && (
              <p className="muted">Бұл нұсқада бөлімшелер берілмеген.</p>
            )}
          </section>
        ))}
      </div>
      <h3>Құрылымдағы өзгерістер</h3>
      {result.unit_changes.length ? (
        <div className="unit-changes">
          {result.unit_changes.map((c) => (
            <article key={c.id}>
              <div className="inline">
                <Badge value={c.change_type} />
                <span className="small muted">{label(c.basis)}</span>
              </div>
              <div className="unit-path">
                <b>
                  {c.before_unit_ids
                    .map((id) => result.units.find((u) => u.id === id)?.name ?? 'Белгісіз')
                    .join(', ') || 'Көрсетілмеген'}
                </b>
                <ArrowRight size={18} />
                <b>
                  {c.after_unit_ids
                    .map((id) => result.units.find((u) => u.id === id)?.name ?? 'Белгісіз')
                    .join(', ') || 'Көрсетілмеген'}
                </b>
              </div>
              <p>{c.explanation}</p>
              <EvidenceLinks ids={c.source_span_ids} onOpen={onEvidence} />
            </article>
          ))}
        </div>
      ) : (
        <Empty
          title="Құрылым өзгерістері берілмеген"
          text="Бөлімшелердің сақталғанын тек дәлелдер арқылы бағалаңыз."
        />
      )}
    </div>
  );
}
export function Results({
  result,
  tab,
  setTab,
  onEvidence,
  review,
  reviews,
  busy,
  onExport,
}: Props) {
  const c = result.coverage;
  const tabs = useMemo(
    () => [
      {
        id: 'risks' as const,
        title: 'Тәуекелдер',
        count: result.findings.length,
        icon: ShieldAlert,
      },
      {
        id: 'functions' as const,
        title: 'Функциялар',
        count: result.mappings.length,
        icon: ArrowRight,
      },
      {
        id: 'structure' as const,
        title: 'Құрылым',
        count: result.unit_changes.length,
        icon: GitBranch,
      },
    ],
    [result],
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">САЛЫСТЫРУ НӘТИЖЕСІ · НҰСҚА {result.analysis_revision}</span>
          <h1>Өзгерістер анық көрінеді.</h1>
          <p>Нәтижелерді қарап, дереккөздермен тексеріңіз және шешіміңізді сақтаңыз.</p>
        </div>
        <button className="button secondary" onClick={onExport}>
          <Download size={16} />
          Есепке өту
        </button>
      </div>
      {result.status === 'partial' && (
        <Alert>
          Нәтиже ішінара: кейбір құжаттар немесе тексерулер толық емес. Шектеулерді ескеріп,
          жетіспейтін материалды нақтылаңыз.
        </Alert>
      )}
      <div className="metrics">
        <article>
          <span className="metric-icon">
            <FileText size={19} />
          </span>
          <span>Оқылған құжаттар</span>
          <strong>
            {c.files_complete}
            <small> / {c.files_total}</small>
          </strong>
          <p>
            {c.files_partial} ішінара · {c.files_failed} қате
          </p>
        </article>
        <article>
          <span className="metric-icon">
            <ArrowRight size={19} />
          </span>
          <span>Бұрынғы функциялар</span>
          <strong>{c.before_functions_total}</strong>
          <p>{c.after_functions_new} жаңа функция кейінгі нұсқада</p>
        </article>
        <article>
          <span className="metric-icon">
            <FileCheck2 size={19} />
          </span>
          <span>Толық сақталған</span>
          <strong>{c.full}</strong>
          <p>
            {c.partial} ішінара · {c.none} табылмаған · {c.unknown} белгісіз
          </p>
        </article>
        <article className="metric-risk">
          <span className="metric-icon">
            <ShieldAlert size={19} />
          </span>
          <span>Тексерілетін жағдайлар</span>
          <strong>{result.findings.length}</strong>
          <p>
            {result.findings.filter((f) => f.review_status === 'unreviewed').length} қаралмаған
            жағдай
          </p>
        </article>
      </div>
      <section className="results-card">
        <div className="result-tabs" role="tablist" aria-label="Нәтиже бөлімдері">
          {tabs.map((t, index) => (
            <button
              key={t.id}
              id={`tab-${t.id}`}
              role="tab"
              aria-selected={tab === t.id}
              aria-controls={`panel-${t.id}`}
              tabIndex={tab === t.id ? 0 : -1}
              className={tab === t.id ? 'active' : ''}
              onClick={() => setTab(t.id)}
              onKeyDown={(e) => {
                let next = index;
                if (e.key === 'ArrowRight') next = (index + 1) % tabs.length;
                else if (e.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
                else if (e.key === 'Home') next = 0;
                else if (e.key === 'End') next = tabs.length - 1;
                else return;
                e.preventDefault();
                setTab(tabs[next].id);
                document.getElementById(`tab-${tabs[next].id}`)?.focus();
              }}
            >
              <t.icon size={17} />
              {t.title}
              <span className="count">{t.count}</span>
            </button>
          ))}
        </div>
        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0}>
          {tab === 'risks' ? (
            <Risks
              result={result}
              onEvidence={onEvidence}
              review={review}
              reviews={reviews}
              busy={busy}
            />
          ) : tab === 'functions' ? (
            <Functions result={result} onEvidence={onEvidence} />
          ) : (
            <Structure result={result} onEvidence={onEvidence} />
          )}
        </div>
      </section>
      <p className="results-footnote">
        <FileCheck2 size={15} />
        {c.evidence_links_valid} / {c.evidence_links_total} дереккөз сілтемесі тексерілген. Санақ —
        модель дәлдігінің пайызы емес.
      </p>
    </>
  );
}
