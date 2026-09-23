import { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ChevronRight,
  CircleHelp,
  Files,
  FlaskConical,
  GitCompareArrows,
  Layers3,
  Menu,
  Plus,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { createLiveApi, saveBlob, type AnalysisApi } from './api/client';
import { createDemoApi } from './demo/provider';
import { useAnalysis } from './hooks/useAnalysis';
import { isProcessing } from './lib/domain';
import { Alert, Badge, Dialog, Empty, Loading, Steps } from './components/common';
import { Upload } from './components/Upload';
import { Progress } from './components/Progress';
import { Results, type ResultTab } from './components/Results';
import { EvidencePanel } from './components/EvidencePanel';
import { Report } from './components/Report';

type Page = 'documents' | 'results' | 'report';
const pageNames = {
  documents: 'Құжаттарды салыстыру',
  results: 'Талдау нәтижелері',
  report: 'Қорытынды есеп',
};
export default function App() {
  const [demo] = useState(() => new URLSearchParams(location.search).get('demo') === '1');
  const [api] = useState<AnalysisApi>(() => (demo ? createDemoApi() : createLiveApi()));
  const a = useAnalysis(api, demo);
  const [page, setPage] = useState<Page>('documents');
  const [tab, setTab] = useState<ResultTab>('risks');
  const [mobileNav, setMobileNav] = useState(false);
  const [help, setHelp] = useState(false);
  const [newAnalysis, setNewAnalysis] = useState(false);
  const [evidence, setEvidence] = useState<{ ids: string[]; title: string } | null>(null);
  const [connection, setConnection] = useState<'checking' | 'online' | 'offline' | 'unconfigured'>(
    'checking',
  );
  const shown = useRef('');
  const processing = isProcessing(a.state?.status);
  const diagnostics = [
    ...new Map(
      [...(a.state?.warnings ?? []), ...(a.result?.warnings ?? [])].map((w) => [
        JSON.stringify(w),
        w,
      ]),
    ).values(),
  ];
  useEffect(() => {
    const controller = new AbortController();
    api
      .health(controller.signal)
      .then((h) => {
        if (!controller.signal.aborted)
          setConnection(h.openai_configured ? 'online' : 'unconfigured');
      })
      .catch(() => {
        if (!controller.signal.aborted) setConnection('offline');
      });
    return () => controller.abort();
  }, [api]);
  useEffect(() => {
    if (a.result) {
      const key = `${a.result.analysis_id}:${a.result.analysis_revision}`;
      if (shown.current !== key) {
        shown.current = key;
        setPage('results');
      }
    }
  }, [a.result]);
  useEffect(() => {
    setEvidence(null);
  }, [a.state?.analysis_revision, a.id]);
  const navigate = (next: Page) => {
    setPage(next);
    setMobileNav(false);
    window.scrollTo({ top: 0, behavior: 'instant' });
  };
  const changeMode = (next: boolean) => {
    const url = new URL(location.href);
    if (next) url.searchParams.set('demo', '1');
    else url.searchParams.delete('demo');
    location.assign(url);
  };
  const openEvidence = (ids: string[], title: string) => {
    if (ids.length) setEvidence({ ids: [...new Set(ids)], title });
  };
  const download = (format: 'html' | 'csv') => {
    void a.transact(async () => {
      if (a.id)
        saveBlob(
          await api.export(a.id, format),
          `qurylym-${demo ? 'demo' : 'report'}-v${a.state?.analysis_revision}.${format}`,
        );
    });
  };
  const reference = (id: string) => {
    const f = a.result?.findings.find((f) => f.id === id);
    const m = a.result?.mappings.find((m) => m.id === id);
    const u = a.result?.unit_changes.find((u) => u.id === id);
    const ids = f
      ? [...f.evidence_ids, ...f.context_evidence_ids]
      : m
        ? [...m.source_span_ids, ...m.context_evidence_ids]
        : (u?.source_span_ids ?? []);
    if (ids.length) openEvidence(ids, f?.title ?? 'Қорытындының дәлелі');
    else a.setError('Бұл қорытындыға ашылатын дәлел тіркелмеген.');
  };
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Негізгі мазмұнға өту
      </a>
      {mobileNav && (
        <button
          className="nav-backdrop"
          aria-label="Мәзірді жабу"
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside className={`sidebar ${mobileNav ? 'open' : ''}`} aria-label="Негізгі мәзір">
        <a href={demo ? '?demo=1' : '?'} className="brand" aria-label="Qurylym AI басты бет">
          <span className="brand-mark">
            <span />
            <i />
          </span>
          <span>
            Qurylym<span className="brand-ai">AI</span>
          </span>
        </a>
        <div className="workspace-label">
          <span className="workspace-avatar">Q</span>
          <div>
            Талдау кеңістігі<small>Ұйымдық өзгерістер</small>
          </div>
          <ChevronRight size={15} />
        </div>
        <span className="nav-caption">ЖҰМЫС КЕҢІСТІГІ</span>
        <nav>
          {[
            { id: 'documents' as const, icon: Files },
            { id: 'results' as const, icon: GitCompareArrows },
            { id: 'report' as const, icon: BookOpen },
          ].map((n) => (
            <button
              key={n.id}
              className={page === n.id ? 'active' : ''}
              disabled={n.id !== 'documents' && !a.result}
              aria-current={page === n.id ? 'page' : undefined}
              onClick={() => navigate(n.id)}
            >
              <n.icon size={19} />
              {pageNames[n.id]}
              {page === n.id && <span className="nav-active-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-guide">
          <span className="guide-symbol">
            <ShieldCheck size={23} />
          </span>
          <h3>Дәлелге сүйенген шешім</h3>
          <p>Әр қорытындыдан құжаттың нақты тармағына өтіңіз.</p>
          <button
            className="text-button"
            onClick={() => {
              setHelp(true);
              setMobileNav(false);
            }}
          >
            Қалай жұмыс істейді
            <ArrowRight size={14} />
          </button>
        </div>
        <div className="sidebar-bottom">
          <button
            onClick={() => {
              setHelp(true);
              setMobileNav(false);
            }}
          >
            <CircleHelp size={18} />
            Қолдану нұсқаулығы
          </button>
          <div className="sidebar-version">
            <span className="tiny-dot" />
            Qurylym AI<span>v1.0</span>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="Мәзірді ашу"
              onClick={() => setMobileNav(true)}
            >
              <Menu size={20} />
            </button>
            <Layers3 size={16} />
            <span>Жұмыс кеңістігі</span>
            <ChevronRight size={13} />
            <strong>{pageNames[page]}</strong>
          </div>
          <div className="topbar-actions">
            <span className={`connection ${demo ? 'demo' : connection}`}>
              <span />
              {demo
                ? 'Демо режимі'
                : connection === 'online'
                  ? 'API қосылған'
                  : connection === 'offline'
                    ? 'API қолжетімсіз'
                    : connection === 'unconfigured'
                      ? 'AI бапталмаған'
                      : 'API тексерілуде'}
            </span>
            <span className="language">ҚАЗ</span>
          </div>
        </header>
        <main id="main" tabIndex={-1}>
          <div className="workspace-toolbar">
            <Steps step={a.result ? 2 : processing ? 1 : 0} />
            <button
              className="text-button new-analysis"
              disabled={a.busy || processing}
              onClick={() => {
                if (a.state) setNewAnalysis(true);
                else navigate('documents');
              }}
            >
              <Plus size={16} />
              Жаңа талдау
            </button>
          </div>
          {demo && (
            <div className="demo-banner" role="note">
              <FlaskConical size={19} />
              <div>
                <strong>Жасанды demo деректері</strong>
                <span>Интерфейс мысалы. Нақты файлдар өңделмеген, AI шақырылмаған.</span>
              </div>
              <button onClick={() => changeMode(false)}>
                Live режимі
                <ArrowRight size={15} />
              </button>
            </div>
          )}
          {a.error && (
            <Alert danger>
              <strong>Әрекетті аяқтау мүмкін болмады</strong>
              <p>{a.error}</p>
              {a.id && (
                <button className="text-button" onClick={a.refresh}>
                  <RefreshCw size={14} />
                  Күйді жаңарту
                </button>
              )}
            </Alert>
          )}
          {a.notice && !a.error && (
            <div className="notice" role="status">
              <Check size={16} />
              {a.notice}
            </div>
          )}
          {a.restoring ? (
            <Loading>Талдау сессиясы қалпына келтірілуде…</Loading>
          ) : processing && a.state ? (
            <Progress state={a.state} />
          ) : page === 'documents' ? (
            <>
              <Upload
                state={a.state}
                busy={a.busy}
                demo={demo}
                upload={a.upload}
                move={a.move}
                run={a.run}
                openDemo={() => changeMode(true)}
              />
              {a.state?.status === 'failed' && (
                <Alert danger>
                  Талдау аяқталмады. Төмендегі диагностиканы тексеріп, салыстыруды қайта бастаңыз.
                </Alert>
              )}
            </>
          ) : a.result ? (
            page === 'results' ? (
              <Results
                result={a.result}
                tab={tab}
                setTab={setTab}
                onEvidence={openEvidence}
                review={a.review}
                reviews={a.reviews}
                busy={a.busy}
                onExport={() => navigate('report')}
              />
            ) : (
              <Report
                result={a.result}
                busy={a.busy}
                demo={demo}
                download={download}
                onReference={reference}
              />
            )
          ) : (
            <Empty title="Нәтиже әлі дайын емес" text="Құжаттарды жүктеп, салыстыруды бастаңыз.">
              <button className="button secondary" onClick={() => navigate('documents')}>
                <ArrowLeft size={16} />
                Құжаттарға оралу
              </button>
            </Empty>
          )}
          {a.state && diagnostics.length > 0 && (
            <details className="diagnostics">
              <summary>
                Диагностика және дерек шектеулері{' '}
                <span className="count">{diagnostics.length}</span>
              </summary>
              {diagnostics.map((w, i) => (
                <div key={`${w.code}-${i}`}>
                  <Badge>{w.code}</Badge>
                  <p>{w.message}</p>
                  {w.document_id && (
                    <span className="small muted">
                      {a.state?.documents.find((d) => d.id === w.document_id)?.filename ??
                        w.document_id}
                    </span>
                  )}
                  {w.span_ids.length > 0 && (
                    <button
                      className="text-button"
                      onClick={() => openEvidence(w.span_ids, 'Диагностика дәлелі')}
                    >
                      Үзінділерді ашу
                    </button>
                  )}
                </div>
              ))}
            </details>
          )}
          <footer className="main-footer">
            <span>
              Qurylym AI <span className="footer-dot">·</span> Өзгерісті түсініңіз. Шешімді
              негіздеңіз.
            </span>
            <span>
              Адам шешім қабылдайды
              <ShieldCheck size={14} />
            </span>
          </footer>
        </main>
      </div>
      {evidence && a.id && (
        <EvidencePanel
          key={`${a.id}:${evidence.ids.join('|')}`}
          api={api}
          analysis={a.id}
          ids={evidence.ids}
          title={evidence.title}
          demo={demo}
          onClose={() => setEvidence(null)}
        />
      )}
      {newAnalysis && (
        <Dialog title="Жаңа талдау бастау" onClose={() => setNewAnalysis(false)}>
          <div className="dialog-content">
            <p>Ағымдағы талдау серверде қалады. Осы бетте жаңа құжаттар жиыны ашылады.</p>
            <p className="small muted">Ағымдағы талдау ID: {a.id}</p>
            <div className="dialog-actions">
              <button className="button secondary" onClick={() => setNewAnalysis(false)}>
                Артқа
              </button>
              <button
                className="button primary"
                onClick={() => {
                  if (demo) changeMode(false);
                  else {
                    a.reset();
                    shown.current = '';
                    navigate('documents');
                    setNewAnalysis(false);
                  }
                }}
              >
                Жаңа талдау
                <Plus size={16} />
              </button>
            </div>
          </div>
        </Dialog>
      )}
      {help && (
        <Dialog title="Qurylym AI қалай жұмыс істейді?" onClose={() => setHelp(false)}>
          <div className="dialog-content help-content">
            <p>
              Ұйымдағы өзгерістерден кейін міндеттердің кімге бекітілгенін құжаттар арқылы
              тексеріңіз.
            </p>
            <ol>
              <li>
                <b>Екі нұсқаны жүктеңіз.</b> «Дейін» және «Кейін» топтарына ережелерді, өкімдерді,
                лауазымдық нұсқаулықтар мен қосымшаларды қосыңыз. Әр файл — 20 МБ-қа дейін, бір
                талдауда — 10 файл.
              </li>
              <li>
                <b>Салыстыруды бастаңыз.</b> Жүйе құжаттарды оқып, функцияларды сәйкестендіреді және
                дәлелдерді тексереді. Бетті жаңартсаңыз, күй қалпына келеді.
              </li>
              <li>
                <b>Дәлелді ашыңыз.</b> Тәуекелдер, функциялар немесе құрылым бөлімінен нақты
                үзіндіге өтіңіз. DOCX тармағы, PDF беті, XLSX парағы мен ұяшығы көрсетіледі.
              </li>
              <li>
                <b>Шешіміңізді сақтаңыз.</b> Жағдайды растаңыз, қабылдамаңыз немесе қосымша ақпарат
                сұраңыз. Соңында HTML немесе CSV есебін жүктеңіз.
              </li>
            </ol>
            <Alert>
              Талдау жүктелген құжаттардың шеңберімен шектеледі. Скан мен сурет оқылмаса, толық
              қорытынды жасауға дерек жеткіліксіз болуы мүмкін.
            </Alert>
            <button className="button primary" onClick={() => setHelp(false)}>
              Түсінікті
              <Check size={16} />
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
