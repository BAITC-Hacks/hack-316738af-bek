import { useEffect, useRef, type ReactNode } from 'react';
import { AlertCircle, Check, ChevronRight, FileSearch, LoaderCircle, X } from 'lucide-react';
import { label } from '../lib/domain';

export function Badge({ value, children }: { value?: string; children?: ReactNode }) {
  const tone = ['full', 'complete', 'completed', 'confirmed', 'preserved', 'validated'].includes(
    value ?? '',
  )
    ? 'green'
    : ['none', 'failed', 'high', 'potential_conflict'].includes(value ?? '')
      ? 'red'
      : [
            'partial',
            'medium',
            'needs_review',
            'needs_information',
            'new',
            'potential_loss',
          ].includes(value ?? '')
        ? 'amber'
        : 'neutral';
  return (
    <span className={`badge ${tone}`}>
      <span className="badge-dot" />
      {children ?? label(value ?? '')}
    </span>
  );
}
export function Loading({ children = 'Жүктелуде…' }: { children?: ReactNode }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={20} />
      {children}
    </div>
  );
}
export function Empty({
  title,
  text,
  children,
}: {
  title: string;
  text: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <FileSearch size={28} />
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
      {children}
    </div>
  );
}
export function Alert({ children, danger = false }: { children: ReactNode; danger?: boolean }) {
  return (
    <div className={`alert ${danger ? 'danger' : ''}`} role={danger ? 'alert' : 'note'}>
      <AlertCircle size={19} />
      <div>{children}</div>
    </div>
  );
}
export function EvidenceLinks({
  ids,
  onOpen,
  title = 'Дереккөздер',
}: {
  ids: string[];
  onOpen: (ids: string[], title: string) => void;
  title?: string;
}) {
  const unique = [...new Set(ids)];
  return unique.length > 0 ? (
    <button className="text-button" onClick={() => onOpen(unique, title)}>
      <FileSearch size={15} />
      {title}
      <span className="count">{unique.length}</span>
      <ChevronRight size={14} />
    </button>
  ) : (
    <span className="muted small">Дәлел тіркелмеген</span>
  );
}
export function Dialog({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const node = ref.current!;
    node.showModal();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      node.close();
      document.body.style.overflow = previousOverflow;
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={`dialog ${wide ? 'wide' : ''}`}
      aria-labelledby="dialog-title"
      onCancel={(e) => {
        e.preventDefault();
        closeRef.current();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="dialog-head">
        <h2 id="dialog-title">{title}</h2>
        <button autoFocus className="icon-button" aria-label="Жабу" onClick={onClose}>
          <X size={21} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Steps({ step }: { step: number }) {
  return (
    <ol className="steps" aria-label="Талдау кезеңдері">
      {['Құжаттарды жүктеу', 'Өзгерістерді талдау', 'Дәлел және шешім'].map((s, i) => (
        <li
          key={s}
          className={step >= i ? 'active' : ''}
          aria-current={step === i ? 'step' : undefined}
        >
          <span>{step > i ? <Check size={15} /> : `0${i + 1}`}</span>
          {s}
          {i < 2 && <ChevronRight size={16} className="step-arrow" />}
        </li>
      ))}
    </ol>
  );
}
