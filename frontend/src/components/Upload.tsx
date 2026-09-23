import { useRef, useState } from 'react';
import {
  ArrowDownToLine,
  ArrowLeftRight,
  ArrowRight,
  Check,
  FileText,
  Layers3,
  Plus,
  ScanLine,
  ShieldCheck,
  UploadCloud,
} from 'lucide-react';
import type { AnalysisState, DocumentSummary } from '../api/types';
import { Badge, Alert } from './common';
import { canRun, fileError, isProcessing, label, MAX_FILES } from '../lib/domain';

type Props = {
  state: AnalysisState | null;
  busy: boolean;
  demo: boolean;
  upload: (files: File[], v: 'before' | 'after') => Promise<unknown>;
  move: (id: string, v: 'before' | 'after') => Promise<unknown>;
  run: () => Promise<unknown>;
  openDemo: () => void;
};
function FileCard({
  doc,
  disabled,
  move,
}: {
  doc: DocumentSummary;
  disabled: boolean;
  move: Props['move'];
}) {
  return (
    <article className="file-card">
      <span className="file-icon">
        <FileText size={20} />
      </span>
      <div className="file-info">
        <strong title={doc.filename}>{doc.filename}</strong>
        <div className="file-meta">
          {label(doc.document_type)}
          {doc.edition ? ` · ${doc.edition}` : ' · Редакция көрсетілмеген'}
        </div>
        <Badge value={doc.parse_status} />{' '}
        <span className="small muted">{doc.span_count} үзінді</span>
        {doc.warnings.map((w, i) => (
          <p key={`${w.code}-${i}`} className="file-warning">
            {w.message}
          </p>
        ))}
        <details className="file-details">
          <summary>Құжат туралы</summary>
          <p>{doc.title}</p>
          <span>SHA-256</span>
          <code>{doc.source_sha256}</code>
        </details>
      </div>
      <button
        className="icon-button"
        disabled={disabled}
        onClick={() => void move(doc.id, doc.version === 'before' ? 'after' : 'before')}
        aria-label={`${doc.filename}: ${doc.version === 'before' ? 'Кейін' : 'Дейін'} тобына ауыстыру`}
        title="Басқа топқа ауыстыру"
      >
        <ArrowLeftRight size={17} />
      </button>
    </article>
  );
}
function Dropzone({
  version,
  documents,
  count,
  busy,
  upload,
  move,
  demo,
}: {
  version: 'before' | 'after';
  documents: DocumentSummary[];
  count: number;
  busy: boolean;
  demo: boolean;
  upload: Props['upload'];
  move: Props['move'];
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState('');
  const choose = async (files: File[]) => {
    setDrag(false);
    setError('');
    if (busy || demo || !files.length) return;
    if (count + files.length > MAX_FILES) {
      setError('Бір талдауға ең көбі 10 файл жүктеуге болады.');
      return;
    }
    const invalid = files
      .map((f) => ({ name: f.name, error: fileError(f) }))
      .filter((f) => f.error);
    if (invalid.length) {
      setError(invalid.map((f) => `${f.name}: ${f.error}`).join(' '));
      return;
    }
    await upload(files, version);
  };
  return (
    <section className={`upload-group ${version}`} aria-labelledby={`group-${version}`}>
      <div className="group-heading">
        <div className="group-title">
          <span className="version-marker">{version === 'before' ? 'A' : 'B'}</span>
          <div>
            <h3 id={`group-${version}`}>{label(version)}</h3>
            <p>
              {version === 'before'
                ? 'Бастапқы құрылым мен міндеттер'
                : 'Жаңартылған құрылым мен міндеттер'}
            </p>
          </div>
        </div>
        <span className="count">{documents.length} файл</span>
      </div>
      <input
        ref={ref}
        id={`file-${version}`}
        aria-label={`${label(version)} құжаттарын таңдау`}
        className="sr-only"
        type="file"
        multiple
        accept=".docx,.pdf,.xlsx"
        disabled={busy || demo}
        onChange={(e) => {
          void choose(Array.from(e.target.files ?? []));
          e.target.value = '';
        }}
      />
      <button
        className={`dropzone ${drag ? 'dragging' : ''}`}
        disabled={busy || demo}
        onClick={() => ref.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy && !demo) setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          void choose(Array.from(e.dataTransfer.files));
        }}
      >
        <span className="upload-icon">
          <UploadCloud size={25} strokeWidth={1.6} />
        </span>
        <strong>Құжаттарды осында сүйреңіз</strong>
        <span>
          немесе <b>файл таңдаңыз</b>
        </span>
        <small>DOCX, PDF, XLSX · әр файл 20 МБ-қа дейін</small>
      </button>
      {error && <Alert danger>{error}</Alert>}
      <div className="file-list">
        {documents.map((doc) => (
          <FileCard key={doc.id} doc={doc} disabled={busy || demo} move={move} />
        ))}
      </div>
      <p className="upload-hint">
        <Plus size={14} />
        Ереже, өкім және қосымшаларды бірге жүктеңіз
      </p>
    </section>
  );
}
export function Upload({ state, busy, demo, upload, move, run, openDemo }: Props) {
  const disabled = busy || isProcessing(state?.status);
  const count = state?.documents.length ?? 0;
  return (
    <>
      <section className="intro">
        <div className="intro-copy">
          <span className="eyebrow">
            <span className="tiny-dot" />
            ҰЙЫМДЫҚ ӨЗГЕРІСТЕРДІ ТАЛДАУ
          </span>
          <h1>
            Әр өзгерістің
            <br />
            <em>дәлелі бар.</em>
          </h1>
          <p>
            Екі нұсқаны салыстырыңыз. Функциялар қалай өзгергенін,
            <br className="desktop-break" /> кімге берілгенін және нені тексеру керегін көріңіз.
          </p>
          <div className="intro-tags">
            <span>
              <ShieldCheck size={15} />
              Нақты дереккөздер
            </span>
            <span>
              <ScanLine size={15} />
              Ашық тексеру
            </span>
          </div>
        </div>
        <div className="org-illustration" aria-hidden="true">
          <span className="diagram-label">ӨЗГЕРІСТІҢ АРТЫНДАҒЫ БАЙЛАНЫС</span>
          <div className="diagram-root">
            <Layers3 size={18} />
            Ұйым құрылымы
          </div>
          <div className="diagram-connector" />
          <div className="diagram-branches">
            <div>
              <span className="diagram-node">Бастапқы бөлім</span>
              <span className="diagram-sub">
                <FileText size={14} />
                Функция
              </span>
            </div>
            <ArrowRight className="diagram-arrow" size={24} />
            <div>
              <span className="diagram-node green">Жаңа жауапты</span>
              <span className="diagram-sub verified">
                <Check size={14} />
                Дәлел
              </span>
            </div>
          </div>
          <span className="diagram-caption">Құрылым → функция → дереккөз</span>
        </div>
      </section>
      <section className="upload-section">
        <div className="section-heading">
          <div>
            <h2>Салыстыруға арналған құжаттар</h2>
            <p>Әр топқа кемінде бір мәтіндік құжат қосыңыз.</p>
          </div>
          <span className="limit-label">{count} / 10 файл</span>
        </div>
        <div className="upload-grid">
          {(['before', 'after'] as const).map((version) => (
            <Dropzone
              key={version}
              version={version}
              documents={state?.documents.filter((d) => d.version === version) ?? []}
              count={count}
              busy={disabled}
              demo={demo}
              upload={upload}
              move={move}
            />
          ))}
        </div>
        <div className="upload-bottom">
          <p>
            <ShieldCheck size={18} />
            Қорытынды тек жүктелген құжаттарға негізделеді.
          </p>
          <button
            className="button primary"
            disabled={disabled || !canRun(state) || demo}
            onClick={() => void run()}
          >
            Салыстыруды бастау
            <ArrowRight size={17} />
          </button>
        </div>
      </section>
      <div className="bottom-grid">
        <section className="demo-card">
          <span className="demo-icon">
            <Layers3 size={24} />
          </span>
          <div>
            <h3>Алдымен қалай жұмыс істейтінін көріңіз</h3>
            <p>Жасанды мысалда нәтижелер мен дәлелдерді ашып көріңіз.</p>
          </div>
          <button className="button secondary" onClick={openDemo}>
            Демоны көру
            <ArrowRight size={16} />
          </button>
        </section>
        <section className="format-note">
          <ArrowDownToLine size={19} />
          <p>
            Мәтіні бар құжаттар қолдау табады.
            <br />
            <span>Скан мен суретке OCR қажет болуы мүмкін.</span>
          </p>
        </section>
      </div>
    </>
  );
}
