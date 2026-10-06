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
import { useState, type ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
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
const statusColors = {
  matched: 'bg-[var(--ds-green-100)] text-[color:var(--ds-green-900)] border-[var(--ds-green-400)]',
  approved:
    'bg-[var(--ds-green-100)] text-[color:var(--ds-green-900)] border-[var(--ds-green-400)]',
  needs_review:
    'bg-[var(--ds-amber-100)] text-[color:var(--ds-amber-900)] border-[var(--ds-amber-400)]',
  duplicate: 'bg-[var(--ds-red-100)] text-[color:var(--ds-red-900)] border-[var(--ds-red-400)]',
  failed: 'bg-[var(--ds-red-100)] text-[color:var(--ds-red-900)] border-[var(--ds-red-400)]',
  rejected: 'bg-[var(--ds-red-100)] text-[color:var(--ds-red-900)] border-[var(--ds-red-400)]',
  processing: 'bg-[var(--ds-blue-100)] text-[color:var(--ds-blue-900)] border-[var(--ds-blue-400)]',
};
export function StatusBadge({ status }: { status: Status }) {
  const [label, Icon] = statuses[status] ?? statuses.failed;
  return (
    <Badge
      variant="outline"
      className={`status status-${status} ${statusColors[status] ?? statusColors.failed}`}
    >
      <Icon size={14} strokeWidth={1.8} />
      {label}
    </Badge>
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
      <div className="not-typeset">{action}</div>
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
  // These dialogs open from several controls, rather than a single DialogTrigger.
  const [previous] = useState(() => document.activeElement as HTMLElement | null);
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent
        className="modal gap-0 bg-card p-0 sm:max-w-[720px]"
        showCloseButton={false}
        aria-describedby={undefined}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          previous?.focus();
        }}
      >
        <DialogTitle className="sr-only">{label}</DialogTitle>
        {children}
      </DialogContent>
    </Dialog>
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
