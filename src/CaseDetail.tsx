import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  AlertCircle,
  ArrowLeft,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  History,
  Info,
  LoaderCircle,
  MapPin,
  Pencil,
  RefreshCw,
  ShieldCheck,
  X,
  XCircle,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { api, apiUrl, date, fieldLabel, jsonRequest, kindLabel, money, navigate } from './api';
import type { Case, Document, Kind } from './types';
import { Empty, FileIcon, Loading, Modal, StatusBadge } from './ui';
import { AuditList } from './Pages';

export default function CaseDetail({
  id,
  changed,
  notify,
}: {
  id: string;
  changed: () => void;
  notify: (message: string) => void;
}) {
  const [data, setData] = useState<Case | null>(null);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('match');
  const [kind, setKind] = useState<Kind>('invoice');
  const [selected, setSelected] = useState('total');
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [value, setValue] = useState('');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [decision, setDecision] = useState<'approve' | 'reject' | null>(null);
  const [note, setNote] = useState('');
  const [decisionError, setDecisionError] = useState('');
  const closeDecision = useCallback(() => {
    if (!saving) {
      setDecision(null);
      setDecisionError('');
    }
  }, [saving]);
  const load = useCallback(async () => {
    try {
      const next = await api<Case>(`/cases/${id}`);
      setData(next);
      setError('');
    } catch (error) {
      setError((error as Error).message);
    }
  }, [id]);
  useEffect(() => {
    setData(null);
    setSelected('total');
    setKind('invoice');
    setTab('match');
    setEditOpen(false);
    load();
    const timer = setInterval(load, 2300);
    return () => clearInterval(timer);
  }, [id, load]);
  const doc = data?.documents?.find((d) => d.kind === kind);
  const field = doc?.fields?.[selected];
  useEffect(() => {
    setValue(String(field?.value ?? ''));
    setReason('');
    setEditOpen(false);
    if (field?.source) setPage(field.source.page);
  }, [kind, selected, field?.value, id]);
  function inspect(kind: Kind, path: string) {
    setKind(kind);
    setSelected(path);
    setEditOpen(false);
    setError('');
  }
  const record = data?.invoice;
  async function saveCorrection(event: React.FormEvent) {
    event.preventDefault();
    if (!doc || !data) return;
    setSaving(true);
    setError('');
    try {
      const updated = await api<Case>(
        `/cases/${id}/documents/${doc.id}`,
        jsonRequest('PATCH', { path: selected, value, reason, expected_revision: data.revision }),
      );
      setData(updated);
      setEditOpen(false);
      changed();
      notify('Correction saved. Reconciliation rules have run again.');
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function submitDecision(event: React.FormEvent) {
    event.preventDefault();
    if (!data || !decision) return;
    setSaving(true);
    setDecisionError('');
    try {
      const updated = await api<Case>(
        `/cases/${id}/decision`,
        jsonRequest('POST', { action: decision, note, expected_revision: data.revision }),
      );
      setData(updated);
      setDecision(null);
      setNote('');
      changed();
      notify(
        decision === 'approve'
          ? 'Approval recorded in the audit history.'
          : 'Rejection recorded in the audit history.',
      );
    } catch (error) {
      setDecisionError((error as Error).message);
    } finally {
      setSaving(false);
    }
  }
  async function retry() {
    try {
      await api(`/cases/${id}/retry`, { method: 'POST' });
      load();
      notify('Document extraction queued again.');
    } catch (error) {
      setError((error as Error).message);
    }
  }
  if (!data)
    return error ? (
      <div className="error-banner">
        {error}
        <button onClick={load}>Retry</button>
      </div>
    ) : (
      <Loading text="Opening the reconciliation…" />
    );
  function Value({
    document,
    path,
    children,
  }: {
    document: Document;
    path: string;
    children?: React.ReactNode;
  }) {
    const current = document.fields?.[path];
    return (
      <button
        className={`source-value ${kind === document.kind && selected === path ? 'source-selected' : ''}`}
        onClick={() => inspect(document.kind, path)}
        title={`Show source for ${fieldLabel(path)}`}
      >
        {children ?? current?.value ?? '—'}
        {current?.corrected ? <Pencil size={10} /> : <MapPin size={11} />}
      </button>
    );
  }
  const fieldType =
    selected === 'date'
      ? 'date'
      : /(?:quantity|unit_price|amount|subtotal|tax|total)$/.test(selected)
        ? 'number'
        : 'text';
  return (
    <div className="case-detail">
      <button className="back-link" onClick={() => navigate('reconciliations')}>
        <ArrowLeft size={15} />
        All reconciliations
      </button>
      <div className="case-heading">
        <div>
          <div className="case-title">
            <FileIcon />
            <h1>{record?.number ?? data.documents?.[0]?.filename ?? 'Processing documents'}</h1>
            <StatusBadge status={data.status} />
          </div>
          <p>
            {record?.supplier ?? 'Document extraction in progress'}
            <span>·</span>
            {record?.po_number ?? 'Waiting for purchase order'}
            <span>·</span>
            {data.is_demo ? 'Sample case' : 'Uploaded case'}
          </p>
        </div>
        <Button asChild variant="outline">
          <a className="button" href={apiUrl(`/cases/${id}/export`)}>
            <Download size={15} />
            Export case
          </a>
        </Button>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          <AlertCircle size={16} />
          {error}
          <button onClick={load}>Refresh</button>
        </div>
      )}
      {data.status === 'processing' ? (
        <div className="processing-panel">
          <div className="processing-orbit">
            <FileText size={30} />
            <LoaderCircle size={60} className="spin" />
          </div>
          <h2>
            {data.job.state === 'queued'
              ? 'Your documents are in the queue.'
              : 'Bringing the details together.'}
          </h2>
          <p>
            Extracting fields and checking the invoice against its purchase order and delivery.
            <br />
            This page updates as soon as your records are ready.
          </p>
          <span className="processing-badge">
            <span className="connection-dot online" />
            {data.job.state === 'queued' ? 'Queued for processing' : 'Processing documents'}
          </span>
        </div>
      ) : (
        <>
          {data.status === 'failed' && (
            <div className="error-banner">
              {data.job.error}
              <button onClick={retry}>
                <RefreshCw size={14} />
                Retry processing
              </button>
            </div>
          )}
          <div className="case-summary">
            <div>
              <span>Invoice amount</span>
              <strong>{record ? money(record.total, record.currency) : '—'}</strong>
            </div>
            <div>
              <span>Invoice date</span>
              <strong>{record ? date(record.date) : '—'}</strong>
            </div>
            <div>
              <span>Documents matched</span>
              <strong>
                {data.documents?.filter((d) => d.record).length} <small>of 3 validated</small>
              </strong>
            </div>
            <div>
              <span>Discrepancies</span>
              <strong className={data.result?.flags.length ? 'amber-text' : 'green-text'}>
                {data.result?.flags.length ?? 0}{' '}
                <small>
                  {data.result?.flags.length ? 'flagged for review' : 'all checks passed'}
                </small>
              </strong>
            </div>
          </div>
          <Tabs value={tab} onValueChange={setTab} className="block">
            <div className="detail-tab-bar">
              <TabsList variant="line" className="detail-tabs" aria-label="Case view">
                {[
                  ['match', 'Three-way match', CheckCircle2],
                  ['records', 'Extracted records', FileText],
                  ['history', 'Audit history', History],
                ].map(([key, label, Icon]) => {
                  const Component = Icon as typeof CheckCircle2;
                  return (
                    <TabsTrigger key={String(key)} value={String(key)}>
                      <Component size={15} />
                      {String(label)}
                      {key === 'history' && <span>{data.audit?.length}</span>}
                    </TabsTrigger>
                  );
                })}
              </TabsList>
              <span className="revision-label">Revision {data.revision}</span>
            </div>
            <TabsContent value={tab} className="mt-0">
              {tab === 'history' ? (
                <section className="content-card audit-card">
                  <div className="card-heading">
                    <h2>A complete decision trail</h2>
                    <span className="muted">Newest first</span>
                  </div>
                  <AuditList events={data.audit ?? []} />
                </section>
              ) : (
                <div className="detail-grid">
                  <div className="record-panel">
                    {tab === 'match' ? (
                      <>
                        <section className="match-results">
                          <div className="card-heading">
                            <h2>
                              {data.result?.flags.length
                                ? 'Let’s take a closer look'
                                : 'Everything lines up'}
                              <span className="count-badge">{data.result?.flags.length ?? 0}</span>
                            </h2>
                            <ShieldCheck size={18} />
                          </div>
                          {data.result?.flags.length ? (
                            <div className="flags-list">
                              {data.result.flags.map((flag, index) => (
                                <div
                                  className={`flag-card flag-${flag.severity}`}
                                  key={`${flag.code}-${index}`}
                                >
                                  <AlertCircle size={18} />
                                  <div>
                                    <h3>{flag.title}</h3>
                                    <p>{flag.message}</p>
                                    <div className="flag-links">
                                      {flag.paths.map((ref) => (
                                        <button
                                          key={`${ref.kind}-${ref.path}`}
                                          onClick={() => inspect(ref.kind, ref.path)}
                                        >
                                          {kindLabel[ref.kind]} · {fieldLabel(ref.path)}
                                          <ArrowUpRight size={12} />
                                        </button>
                                      ))}
                                      {flag.code === 'duplicate_invoice' &&
                                        data.result?.duplicate_cases?.map((caseId) => (
                                          <button
                                            key={caseId}
                                            onClick={() => navigate(`case/${caseId}`)}
                                          >
                                            Open original case <ArrowUpRight size={12} />
                                          </button>
                                        ))}
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="matched-message">
                              <span>
                                <CheckCheckIcon />
                              </span>
                              <div>
                                <strong>All three documents agree.</strong>
                                <p>
                                  Item codes, quantities, prices, and totals passed the
                                  reconciliation checks.
                                </p>
                              </div>
                            </div>
                          )}
                        </section>
                        <section className="comparison-card">
                          <div className="card-heading">
                            <h2>Line item comparison</h2>
                            <span className="muted">Click a value to see its source</span>
                          </div>
                          <div className="comparison-scroll">
                            <table className="comparison-table">
                              <thead>
                                <tr>
                                  <th>Item</th>
                                  <th>Ordered</th>
                                  <th>Invoiced</th>
                                  <th>Received</th>
                                  <th>Check</th>
                                </tr>
                              </thead>
                              <tbody>
                                {data.result?.lines.map((line) => (
                                  <tr key={line.sku}>
                                    <td>
                                      <strong>{line.sku}</strong>
                                      <small>{line.description}</small>
                                    </td>
                                    {(['purchase_order', 'invoice', 'delivery'] as Kind[]).map(
                                      (k, i) => {
                                        const document = data.documents?.find((d) => d.kind === k);
                                        const index = document?.record?.line_items.findIndex(
                                          (item) => item.sku === line.sku,
                                        );
                                        return (
                                          <td
                                            key={k}
                                            className={line.issues.length ? 'quantity-flagged' : ''}
                                          >
                                            <span className="mobile-field-label">
                                              {['Ordered', 'Invoiced', 'Received'][i]}
                                            </span>
                                            {document && index !== undefined && index >= 0 ? (
                                              <Value
                                                document={document}
                                                path={`line_items.${index}.quantity`}
                                              >
                                                {[line.ordered, line.invoiced, line.received][i]}
                                              </Value>
                                            ) : (
                                              '—'
                                            )}
                                          </td>
                                        );
                                      },
                                    )}
                                    <td>
                                      {line.issues.length ? (
                                        <span className="line-warning">
                                          <AlertCircle size={13} />
                                          {line.issues.join(', ')}
                                        </span>
                                      ) : (
                                        <span className="line-matched">
                                          <Check size={15} />
                                          Matched
                                        </span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          {!data.result?.lines.length && (
                            <Empty title="Records need attention">
                              The document set could not be validated. Check the extraction errors
                              below.
                            </Empty>
                          )}
                        </section>
                        {data.documents
                          ?.filter((d) => d.errors?.length)
                          .map((d) => (
                            <div className="error-banner extraction-error" key={d.id}>
                              <AlertCircle size={16} />
                              <div>
                                <strong>{kindLabel[d.kind]} extraction failed</strong>
                                {d.errors?.map((error, i) => (
                                  <p key={i}>{error}</p>
                                ))}
                                <button onClick={retry}>
                                  <RefreshCw size={13} />
                                  Retry extraction
                                </button>
                              </div>
                            </div>
                          ))}
                        <div className="decision-card">
                          <div className="decision-icon">
                            <ShieldCheck size={23} />
                          </div>
                          <h3>Your review. Your decision.</h3>
                          <p>
                            {data.result?.flags.length
                              ? 'Correct extracted values or acknowledge the differences before recording your decision.'
                              : 'The checks passed. Record an approval when you’re ready.'}
                          </p>
                          <div>
                            <Button
                              variant="outline"
                              type="button"
                              className="button"
                              onClick={() => {
                                setDecision('reject');
                                setNote('');
                              }}
                              disabled={data.status === 'rejected' || data.status === 'failed'}
                            >
                              <XCircle size={15} />
                              Reject invoice
                            </Button>
                            <Button
                              variant="default"
                              type="button"
                              className="button button-dark"
                              onClick={() => {
                                setDecision('approve');
                                setNote('');
                              }}
                              disabled={
                                data.status === 'approved' ||
                                data.status === 'failed' ||
                                data.documents?.some((d) => !d.record)
                              }
                            >
                              <CheckCircle2 size={15} />
                              {data.status === 'approved' ? 'Approved' : 'Approve invoice'}
                            </Button>
                          </div>
                        </div>
                      </>
                    ) : (
                      <section className="extracted-card">
                        <div className="card-heading">
                          <h2>Extracted values</h2>
                          <span className="muted">Source-linked & editable</span>
                        </div>
                        {data.documents?.map((document) => (
                          <div className="extracted-group" key={document.id}>
                            <h3>
                              <FileIcon kind={document.kind} small />
                              {kindLabel[document.kind]}
                              <span>{Object.keys(document.fields ?? {}).length} fields</span>
                            </h3>
                            {document.record ? (
                              <>
                                <div className="field-grid">
                                  {[
                                    'supplier',
                                    'number',
                                    'po_number',
                                    'date',
                                    'currency',
                                    'subtotal',
                                    'tax',
                                    'total',
                                  ]
                                    .filter((path) => document.fields?.[path])
                                    .map((path) => (
                                      <div className="field-item" key={path}>
                                        <label>{fieldLabel(path)}</label>
                                        <Value document={document} path={path} />
                                      </div>
                                    ))}
                                </div>
                                <div className="extracted-lines">
                                  {document.record.line_items.map((item, index) => (
                                    <div key={index}>
                                      <h4>
                                        Line {index + 1} · {item.sku}
                                      </h4>
                                      <div className="field-grid">
                                        {['sku', 'description', 'quantity', 'unit_price', 'amount']
                                          .filter(
                                            (name) =>
                                              document.fields?.[`line_items.${index}.${name}`],
                                          )
                                          .map((name) => (
                                            <div key={name} className="field-item">
                                              <label>{fieldLabel(name)}</label>
                                              <Value
                                                document={document}
                                                path={`line_items.${index}.${name}`}
                                              />
                                            </div>
                                          ))}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </>
                            ) : (
                              <div className="extraction-error">
                                <p>{document.errors?.join(' ')}</p>
                                <Button
                                  variant="outline"
                                  type="button"
                                  className="button"
                                  onClick={retry}
                                >
                                  Retry extraction
                                </Button>
                              </div>
                            )}
                          </div>
                        ))}
                      </section>
                    )}
                  </div>
                  <aside className="source-panel">
                    <div className="source-panel-header">
                      <div>
                        <MapPin size={16} />
                        <h2>Source document</h2>
                      </div>
                      <Button asChild variant="outline" size="icon">
                        <a
                          className="icon-button"
                          href={apiUrl(`/documents/${doc?.id}/file`)}
                          aria-label="Download original document"
                          title="Download original"
                        >
                          <Download size={16} />
                        </a>
                      </Button>
                    </div>
                    <div className="document-switcher" role="group" aria-label="Source document">
                      {(['invoice', 'purchase_order', 'delivery'] as Kind[]).map((k) => (
                        <Button
                          key={k}
                          type="button"
                          variant={kind === k ? 'secondary' : 'ghost'}
                          aria-pressed={kind === k}
                          className="h-auto min-h-10 px-3 py-1"
                          onClick={() => {
                            setKind(k);
                            setSelected(k === 'delivery' ? 'number' : 'total');
                            setPage(1);
                            setZoom(1);
                          }}
                        >
                          {k === 'purchase_order'
                            ? 'Purchase order'
                            : k === 'delivery'
                              ? 'Delivery'
                              : 'Invoice'}
                        </Button>
                      ))}
                    </div>
                    <div className="source-file-name">
                      <FileText size={13} />
                      <span>{doc?.filename}</span>
                      <span>{doc?.method === 'ocr' ? 'OCR' : 'PDF'}</span>
                    </div>
                    <div className="viewer-toolbar">
                      <span>
                        Page {page} of {doc?.pages?.length || 0}
                      </span>
                      <div>
                        <Button
                          variant="ghost"
                          size="icon"
                          type="button"
                          className="icon-button"
                          aria-label="Previous document page"
                          disabled={page <= 1}
                          onClick={() => setPage(page - 1)}
                        >
                          <ChevronLeft size={15} />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          type="button"
                          className="icon-button"
                          aria-label="Next document page"
                          disabled={page >= (doc?.pages?.length || 1)}
                          onClick={() => setPage(page + 1)}
                        >
                          <ChevronRight size={15} />
                        </Button>
                        <span className="toolbar-divider" />
                        <Button
                          variant="ghost"
                          size="icon"
                          type="button"
                          className="icon-button"
                          aria-label="Zoom out"
                          disabled={zoom <= 1}
                          onClick={() => setZoom((v) => Math.max(1, v - 0.25))}
                        >
                          <ZoomOut size={15} />
                        </Button>
                        <span>{Math.round(zoom * 100)}%</span>
                        <Button
                          variant="ghost"
                          size="icon"
                          type="button"
                          className="icon-button"
                          aria-label="Zoom in"
                          disabled={zoom >= 2}
                          onClick={() => setZoom((v) => Math.min(2, v + 0.25))}
                        >
                          <ZoomIn size={15} />
                        </Button>
                      </div>
                    </div>
                    <div className="document-viewer">
                      {doc?.pages?.length ? (
                        <div
                          className="document-image not-typeset"
                          style={{ width: `${zoom * 100}%` }}
                        >
                          <img
                            src={apiUrl(`/documents/${doc.id}/pages/${page}`)}
                            alt={`${kindLabel[kind]} ${doc.filename}, page ${page}`}
                          />
                          {field?.source?.page === page && (
                            <span
                              className={`source-highlight ${field.corrected ? 'corrected-highlight' : ''}`}
                              style={{
                                left: `${field.source.bbox[0] * 100}%`,
                                top: `${field.source.bbox[1] * 100}%`,
                                width: `${(field.source.bbox[2] - field.source.bbox[0]) * 100}%`,
                                height: `${(field.source.bbox[3] - field.source.bbox[1]) * 100}%`,
                              }}
                              title={`Source: ${field.source.text}`}
                            />
                          )}
                        </div>
                      ) : (
                        <Empty title="No preview available">
                          This document could not be rendered. Download the original to inspect it.
                        </Empty>
                      )}
                    </div>
                    <div className="evidence-panel">
                      {field ? (
                        <>
                          <div className="evidence-heading">
                            <span>
                              <MapPin size={13} />
                              {fieldLabel(selected)}
                            </span>
                            <span className={field.corrected ? 'corrected-label' : ''}>
                              {field.corrected ? (
                                <>
                                  <Pencil size={11} />
                                  Corrected
                                </>
                              ) : field.source ? (
                                <>
                                  <Check size={12} />
                                  Source linked
                                </>
                              ) : (
                                'Source unverified'
                              )}
                            </span>
                          </div>
                          <div className="evidence-value">
                            {String(field.value)}
                            <Button
                              variant="outline"
                              type="button"
                              className="button edit-button"
                              onClick={() => {
                                setEditOpen((v) => !v);
                                setValue(String(field.value));
                                setReason('');
                              }}
                            >
                              <Pencil size={12} />
                              Correct value
                            </Button>
                          </div>
                          {field.source ? (
                            <p className="source-quote">
                              “{field.source.text}” <span>· Page {field.source.page}</span>
                            </p>
                          ) : (
                            <p className="source-quote">
                              A source location could not be verified. Check the original document.
                            </p>
                          )}
                          {field.corrected && (
                            <p className="original-value">
                              Originally extracted: <strong>{field.extracted_value}</strong>
                            </p>
                          )}
                          {editOpen && (
                            <form className="correction-form" onSubmit={saveCorrection}>
                              <label htmlFor="corrected-value">Corrected value</label>
                              <Input
                                id="corrected-value"
                                type={fieldType}
                                step="any"
                                min={fieldType === 'number' ? '0' : undefined}
                                value={value}
                                onChange={(e) => setValue(e.target.value)}
                                required
                                autoFocus
                              />
                              <label htmlFor="correction-reason">Reason for correction</label>
                              <Textarea
                                id="correction-reason"
                                placeholder="What did you verify in the original document?"
                                value={reason}
                                onChange={(e) => setReason(e.target.value)}
                                minLength={3}
                                maxLength={1000}
                                required
                                rows={2}
                              />
                              <p>
                                <History size={12} />
                                Original extraction and source remain in the audit trail.
                              </p>
                              <div>
                                <Button
                                  variant="outline"
                                  type="button"
                                  className="button"
                                  onClick={() => setEditOpen(false)}
                                  disabled={saving}
                                >
                                  Cancel
                                </Button>
                                <Button
                                  variant="default"
                                  type="submit"
                                  className="button button-dark"
                                  disabled={saving || value === String(field.value)}
                                >
                                  {saving ? (
                                    <LoaderCircle className="spin" size={13} />
                                  ) : (
                                    <Check size={13} />
                                  )}
                                  Save correction
                                </Button>
                              </div>
                            </form>
                          )}
                        </>
                      ) : (
                        <p className="evidence-placeholder">
                          <Info size={15} />
                          Click an extracted value to see its original source and make a traceable
                          correction.
                        </p>
                      )}
                    </div>
                  </aside>
                </div>
              )}
            </TabsContent>
          </Tabs>
        </>
      )}
      <div className="case-footer">
        <ShieldCheck size={13} />
        <span>Exact item codes · Decimal arithmetic · Three-way matching</span>
        <span>Case {id.slice(0, 8).toUpperCase()}</span>
      </div>
      {decision && (
        <Modal
          close={closeDecision}
          label={decision === 'approve' ? 'Approve invoice' : 'Reject invoice'}
        >
          <form onSubmit={submitDecision}>
            <div className="modal-header">
              <div>
                <span className="eyebrow">MAKE IT PART OF THE RECORD</span>
                <h2>{decision === 'approve' ? 'Approve this invoice?' : 'Reject this invoice?'}</h2>
                <p>
                  {record?.number} · {record?.supplier}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                type="button"
                className="icon-button"
                aria-label="Close decision"
                onClick={closeDecision}
                disabled={saving}
              >
                <X size={20} />
              </Button>
            </div>
            <div className="decision-modal-body">
              {decision === 'approve' && !!data.result?.flags.length && (
                <div className="decision-warning">
                  <AlertCircle size={19} />
                  <div>
                    <strong>{data.result.flags.length} discrepancies are still flagged.</strong>
                    <p>
                      Your approval acknowledges these differences. Explain why you’re accepting
                      them in the note below.
                    </p>
                  </div>
                </div>
              )}
              <label htmlFor="decision-note">
                Review note <span>Required</span>
              </label>
              <Textarea
                id="decision-note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                minLength={3}
                maxLength={2000}
                rows={4}
                placeholder={
                  decision === 'approve'
                    ? 'Record what you checked and why this invoice is approved…'
                    : 'Explain why this invoice should not be processed…'
                }
                required
                autoFocus
              />
              <p>
                <History size={13} />
                This decision, note, and current discrepancies will be added to the audit history.
              </p>
              {decisionError && (
                <div className="error-banner" role="alert">
                  {decisionError}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <Button
                variant="outline"
                type="button"
                className="button"
                onClick={closeDecision}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button
                variant="default"
                type="submit"
                className={`button ${decision === 'approve' ? 'button-dark' : 'button-danger'}`}
                disabled={saving}
              >
                {saving ? (
                  <LoaderCircle className="spin" size={15} />
                ) : decision === 'approve' ? (
                  <CheckCircle2 size={15} />
                ) : (
                  <XCircle size={15} />
                )}
                {decision === 'approve' ? 'Record approval' : 'Record rejection'}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

function CheckCheckIcon() {
  return <CheckCircle2 size={24} strokeWidth={1.5} />;
}
