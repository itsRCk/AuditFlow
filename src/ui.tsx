import {
  AlertCircle,
  Check,
  CheckCircle2,
  Clock3,
  Copy,
  FileText,
  LoaderCircle,
  Search,
  X,
  XCircle,
} from 'lucide-react';
import { useState, type ComponentProps, type ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import type { Status } from './types';

export function SearchField({
  onClear,
  ...props
}: ComponentProps<'input'> & { onClear: () => void }) {
  return (
    <div className="search-field">
      <Search className="search-field-icon" size={16} aria-hidden="true" />
      <Input {...props} className="pl-10 pr-10" />
      {!!props.value && (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="search-field-clear"
          aria-label="Clear search"
          onClick={onClear}
        >
          <X size={14} />
        </Button>
      )}
    </div>
  );
}

export function SummaryCard({
  label,
  value,
  caption,
  icon: Icon,
  detail,
}: {
  label: string;
  value: ReactNode;
  caption: string;
  icon: typeof Check;
  detail?: ReactNode;
}) {
  return (
    <Card className="summary-card gap-0 overflow-hidden p-0 shadow-none">
      <CardHeader className="flex flex-row items-start justify-between gap-3 px-5 pt-5 pb-0">
        <span className="summary-label">{label}</span>
        <span className="summary-icon">
          <Icon size={16} aria-hidden="true" />
        </span>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col px-5 pt-3 pb-5">
        <strong className="summary-value">{value}</strong>
        {detail && <div className="summary-detail">{detail}</div>}
        <p className="summary-caption">{caption}</p>
      </CardContent>
    </Card>
  );
}

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
