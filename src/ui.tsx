import {
  AlertCircle,
  Check,
  CheckCircle2,
  Clock3,
  Copy,
  FileText,
  LoaderCircle,
  XCircle,
} from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';
import type { Status } from './types';

const statuses = {
  matched: ['Matched', CheckCircle2],
  approved: ['Approved', CheckCircle2],
  needs_review: ['Needs review', AlertCircle],
  duplicate: ['Duplicate', Copy],
  processing: ['Processing', Clock3],
  rejected: ['Rejected', XCircle],
  failed: ['Processing failed', AlertCircle],
} as const;
export function StatusBadge({ status }: { status: Status }) {
  const [label, Icon] = statuses[status] ?? statuses.failed;
  return (
    <span className={`status status-${status}`}>
      <Icon size={12} strokeWidth={1.8} />
      {label}
    </span>
  );
}
export function FileIcon({ kind = 'invoice', small = false }: { kind?: string; small?: boolean }) {
  return (
    <span className={`file-icon file-${kind} ${small ? 'file-small' : ''}`}>
      <FileText size={small ? 15 : 19} strokeWidth={1.6} />
    </span>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-symbol">
        <FileText size={28} />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Loading({ text = 'Loading your workspace…' }: { text?: string }) {
  return (
    <div className="loading">
      <LoaderCircle className="spin" size={24} />
      <span>{text}</span>
    </div>
  );
}
export function Modal({
  children,
  close,
  label,
}: {
  children: ReactNode;
  close: () => void;
  label: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const previous = document.activeElement as HTMLElement | null;
    const focusable = () =>
      container.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled):not([tabindex="-1"]), textarea:not(:disabled), select, a[href], [tabindex="0"]',
      );
    focusable()?.[0]?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
      if (event.key === 'Tab') {
        const elements = focusable();
        if (!elements?.length) return;
        const first = elements[0],
          last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', key);
    return () => {
      document.body.style.overflow = oldOverflow;
      document.removeEventListener('keydown', key);
      previous?.focus();
    };
  }, [close]);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div className="modal" ref={container} role="dialog" aria-modal="true" aria-label={label}>
        {children}
      </div>
    </div>
  );
}
export function Toast({ message }: { message: string }) {
  return (
    <div className="toast" role="status">
      <Check size={16} />
      {message}
    </div>
  );
}
