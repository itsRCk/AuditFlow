import {
  Activity,
  AlertCircle,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Download,
  FileText,
  Info,
  MapPin,
  Pencil,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  X,
  XCircle,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, apiUrl, date, fieldLabel, kindLabel, money, navigate } from './api';
import type { AuditEvent, Case, Document, Kind, Metrics } from './types';
import { Empty, FileIcon, Loading, StatusBadge } from './ui';

const actionInfo: { [key: string]: { title: string; icon: typeof Check; className: string } } = {
  uploaded: { title: 'Documents uploaded', icon: UploadCloud, className: 'audit-blue' },
  extracted: { title: 'Document fields extracted', icon: FileText, className: 'audit-gray' },
  reconciled: { title: 'Reconciliation completed', icon: CheckCircle2, className: 'audit-green' },
  corrected: { title: 'Extracted value corrected', icon: Pencil, className: 'audit-amber' },
  approve: { title: 'Invoice approved', icon: CheckCircle2, className: 'audit-green' },
  reject: { title: 'Invoice rejected', icon: XCircle, className: 'audit-red' },
  decision_invalidated: {
    title: 'Previous decision invalidated',
    icon: AlertCircle,
    className: 'audit-amber',
  },
  exported: { title: 'Case evidence exported', icon: Download, className: 'audit-gray' },
  processing_failed: {
    title: 'Document processing failed',
    icon: AlertCircle,
    className: 'audit-red',
  },
  retried: { title: 'Processing queued again', icon: RefreshCw, className: 'audit-blue' },
};

export function AuditList({ events, cases }: { events: AuditEvent[]; cases?: Case[] }) {
  return (
    <div className="audit-list">
      {events.length ? (
        events.map((event) => {
          const info = actionInfo[event.action] ?? {
            title: event.action,
            icon: Activity,
            className: 'audit-gray',
          };
          const Icon = info.icon;
          const record = cases?.find((c) => c.id === event.case_id)?.invoice;
          const payload = event.payload;
          return (
            <div className="audit-entry" key={event.sequence}>
              <div className={`audit-icon ${info.className}`}>
                <Icon size={16} />
              </div>
              <div className="audit-entry-body">
                <div className="audit-title">
                  <strong>{info.title}</strong>
                  <time>
                    {date(event.created_at, {
                      day: '2-digit',
                      month: 'short',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </time>
                </div>
                <p>
                  {event.actor}
                  {event.action === 'extracted'
                    ? ` · ${kindLabel[payload.kind as Kind]} · ${payload.field_count} fields`
                    : event.action === 'reconciled'
                      ? ` · ${String(payload.status).replace('_', ' ')} · ${(payload.flags as unknown[])?.length ?? 0} discrepancies`
                      : event.action === 'uploaded'
                        ? ` · ${(payload.filenames as string[])?.length ?? 3} source documents`
                        : event.action === 'exported'
                          ? ` · Revision ${payload.revision}`
                          : ''}
                  {record && (
                    <button
                      className="audit-case-link"
                      onClick={() => navigate(`case/${event.case_id}`)}
                    >
                      {record.number}
                      <ArrowUpRight size={11} />
                    </button>
                  )}
                </p>
                {event.action === 'corrected' && (
                  <div className="correction-history">
                    <span>{fieldLabel(String(payload.path))}</span>
                    <del>{String(payload.before)}</del>
                    <ArrowRight size={13} />
                    <strong>{String(payload.after)}</strong>
                    <p>{String(payload.reason)}</p>
                    <small>Original extraction: {String(payload.extracted_value)}</small>
                  </div>
                )}
                {!!payload.note && <blockquote>{String(payload.note)}</blockquote>}
                {event.action === 'decision_invalidated' && (
                  <blockquote>{String(payload.reason)}</blockquote>
                )}
              </div>
            </div>
          );
        })
      ) : (
        <Empty title="The story starts here">
          Your uploads, corrections, and review decisions will appear here.
        </Empty>
      )}
    </div>
  );
}

export function ActivityPage({ cases }: { cases: Case[] }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  async function load() {
    try {
      setEvents(await api('/events'));
      setError('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);
  const visible = events.filter(
    (e) =>
      filter === 'all' ||
      (filter === 'review' && ['approve', 'reject', 'decision_invalidated'].includes(e.action)) ||
      (filter === 'corrections' && e.action === 'corrected') ||
      (filter === 'processing' &&
        ['uploaded', 'extracted', 'reconciled', 'processing_failed', 'retried'].includes(e.action)),
  );
  return (
    <section className="content-card activity-page">
      <div className="card-heading">
        <div>
          <h2>Every action, accounted for.</h2>
          <p>The latest 300 immutable events in your workspace.</p>
        </div>
        <button className="button" onClick={load}>
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>
      <div className="page-filter-tabs">
        {[
          ['all', 'All activity'],
          ['review', 'Review decisions'],
          ['corrections', 'Corrections'],
          ['processing', 'Document processing'],
        ].map(([key, label]) => (
          <button
            key={key}
            className={filter === key ? 'active' : ''}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {error && <div className="error-banner">{error}</div>}
      {loading ? <Loading /> : <AuditList events={visible} cases={cases} />}
    </section>
  );
}

export function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  async function load() {
    try {
      setDocuments(await api('/documents'));
      setError('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);
  const visible = documents.filter(
    (d) =>
      (filter === 'all' || d.kind === filter) &&
      `${d.filename} ${d.record?.supplier} ${d.record?.number}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <>
      <div className="documents-toolbar">
        <div className="page-filter-tabs">
          {[
            ['all', 'All documents'],
            ['invoice', 'Invoices'],
            ['purchase_order', 'Purchase orders'],
            ['delivery', 'Delivery records'],
          ].map(([key, label]) => (
            <button
              key={key}
              className={filter === key ? 'active' : ''}
              onClick={() => setFilter(key)}
            >
              {label}
              <span>{documents.filter((d) => key === 'all' || d.kind === key).length}</span>
            </button>
          ))}
        </div>
        <div className="documents-tools">
          <label className="table-search">
            <Search size={15} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search documents…"
              aria-label="Search documents"
            />
          </label>
          <button className="icon-button" onClick={load} aria-label="Refresh documents">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}
      {loading ? (
        <Loading />
      ) : visible.length ? (
        <div className="documents-grid">
          {visible.map((document) => (
            <article key={document.id} className="document-card">
              <div
                className={`doc-preview doc-preview-${document.kind}`}
                onClick={() => navigate(`case/${document.case_id}`)}
              >
                {document.pages?.length ? (
                  <img
                    src={apiUrl(`/documents/${document.id}/pages/1`)}
                    alt={`${kindLabel[document.kind]} preview`}
                    loading="lazy"
                  />
                ) : (
                  <FileText size={40} />
                )}
                <span>{document.filename.split('.').at(-1)?.toUpperCase()}</span>
              </div>
              <div className="document-card-body">
                <div className="document-card-title">
                  <FileIcon kind={document.kind} small />
                  <div>
                    <h3>{document.record?.number ?? document.filename}</h3>
                    <p>{document.record?.supplier ?? 'Extraction pending'}</p>
                  </div>
                  <a
                    className="icon-button"
                    href={apiUrl(`/documents/${document.id}/file`)}
                    aria-label={`Download ${document.filename}`}
                  >
                    <Download size={16} />
                  </a>
                </div>
                <div className="document-card-meta">
                  <span>{kindLabel[document.kind]}</span>
                  <span>{(document.size / 1024).toFixed(0)} KB</span>
                </div>
                <div className="document-card-footer">
                  <span>
                    <MapPin size={12} />
                    {Object.values(document.fields ?? {}).filter((f) => f.source).length}{' '}
                    source-linked fields
                  </span>
                  <button onClick={() => navigate(`case/${document.case_id}`)}>
                    Open case <ArrowUpRight size={13} />
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <Empty title="No documents found">
          Try a different search or upload a new reconciliation.
        </Empty>
      )}
    </>
  );
}

function MetricCard({
  label,
  value,
  caption,
  icon: Icon,
}: {
  label: string;
  value: string;
  caption: string;
  icon: typeof Check;
}) {
  return (
    <div className="metric-card">
      <span className="metric-icon">
        <Icon size={19} />
      </span>
      <p>{label}</p>
      <strong>{value}</strong>
      <small>{caption}</small>
    </div>
  );
}

export function MetricsPage() {
  const [data, setData] = useState<Metrics | null>(null);
  const [error, setError] = useState('');
  const load = async () => {
    try {
      setData(await api('/metrics'));
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };
  useEffect(() => {
    load();
  }, []);
  if (!data)
    return error ? (
      <div className="error-banner">
        {error}
        <button onClick={load}>Retry</button>
      </div>
    ) : (
      <Loading text="Loading measurement results…" />
    );
  const evaluation = data.evaluation;
  const percentage = (value?: number | null) =>
    value == null ? '—' : `${(value * 100).toFixed(1)}%`;
  return (
    <>
      <div className="metric-scope">
        <span>
          <Sparkles size={16} />
          <strong>Measured, not assumed.</strong>
        </span>
        <p>
          Accuracy is measured against labelled sample documents. Workspace activity reflects actual
          processing and reviews.
        </p>
        <button className="button" onClick={load}>
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>
      <div className="metric-grid">
        <MetricCard
          label="Field extraction accuracy"
          value={percentage(evaluation?.field_accuracy)}
          caption={
            evaluation
              ? `${evaluation.fields_correct} of ${evaluation.fields_total} fields correct`
              : 'Fixture evaluation has not run'
          }
          icon={FileText}
        />
        <MetricCard
          label="Discrepancy precision"
          value={percentage(evaluation?.discrepancy_precision)}
          caption={
            evaluation
              ? `${evaluation.false_positives} false positives in sample cases`
              : 'No benchmark available'
          }
          icon={ShieldCheck}
        />
        <MetricCard
          label="Discrepancy recall"
          value={percentage(evaluation?.discrepancy_recall)}
          caption={
            evaluation
              ? `${evaluation.false_negatives} missed discrepancies in sample cases`
              : 'No benchmark available'
          }
          icon={CheckCircle2}
        />
        <MetricCard
          label="API cost per document"
          value={data.cost_per_document === null ? 'Unknown' : money(data.cost_per_document)}
          caption="Provider charges only; excludes infrastructure"
          icon={ArrowDownToLine}
        />
      </div>
      <div className="performance-grid">
        <section className="content-card benchmark-card">
          <div className="card-heading">
            <div>
              <span className="eyebrow">THE FIXTURE BENCHMARK</span>
              <h2>Small dataset. Clear evidence.</h2>
            </div>
            <span className="subtle-badge">{evaluation?.documents ?? 0} documents</span>
          </div>
          {evaluation ? (
            <>
              <div className="benchmark-facts">
                <div>
                  <strong>{evaluation.layouts}</strong>
                  <span>English layouts</span>
                </div>
                <div>
                  <strong>{evaluation.scanned_documents}</strong>
                  <span>Scanned invoice</span>
                </div>
                <div>
                  <strong>{evaluation.scenarios.length}</strong>
                  <span>Three-document cases</span>
                </div>
              </div>
              <div className="benchmark-scenarios">
                {evaluation.scenarios.map((scenario, i) => (
                  <div key={i}>
                    <span className={`scenario-check ${scenario.passed ? '' : 'scenario-failed'}`}>
                      {scenario.passed ? <Check size={13} /> : <X size={13} />}
                    </span>
                    <div>
                      <strong>{scenario.supplier}</strong>
                      <span>
                        {scenario.scenario === 'matched'
                          ? 'Matching invoice, PO, and delivery'
                          : scenario.scenario === 'duplicate'
                            ? 'Duplicate invoice detection'
                            : `${scenario.scenario.charAt(0).toUpperCase() + scenario.scenario.slice(1)} discrepancy`}
                      </span>
                    </div>
                    <span className="benchmark-result">
                      {scenario.passed ? 'Passed' : 'Failed'}
                    </span>
                  </div>
                ))}
              </div>
              <div className="benchmark-note">
                <Info size={15} />
                <p>
                  {evaluation.limitation} Evaluated {date(evaluation.evaluated_at)}.
                </p>
              </div>
            </>
          ) : (
            <Empty title="No benchmark yet">
              Run the documented fixture evaluation to measure extraction and discrepancy results.
            </Empty>
          )}
        </section>
        <div className="performance-side">
          <section className="content-card">
            <div className="card-heading">
              <h2>Workspace activity</h2>
              <Activity size={17} />
            </div>
            <div className="activity-metrics">
              <div>
                <span>Documents processed</span>
                <strong>{data.documents_processed}</strong>
              </div>
              <div>
                <span>Average processing time / case</span>
                <strong>
                  {data.average_processing_ms === null
                    ? '—'
                    : `${(data.average_processing_ms / 1000).toFixed(2)} s`}
                </strong>
              </div>
              <div>
                <span>Provider API cost</span>
                <strong>{data.api_cost_usd === null ? 'Unknown' : money(data.api_cost_usd)}</strong>
              </div>
            </div>
          </section>
          <section className="content-card correction-effort">
            <span className="metric-icon">
              <Pencil size={20} />
            </span>
            <h2>Correction effort</h2>
            <strong className="effort-number">
              {data.corrections}
              <small>field corrections</small>
            </strong>
            <div className="activity-metrics">
              <div>
                <span>Cases reviewed</span>
                <strong>{data.reviewed_cases}</strong>
              </div>
              <div>
                <span>Corrections / reviewed case</span>
                <strong>
                  {data.corrections_per_reviewed_case == null
                    ? '—'
                    : data.corrections_per_reviewed_case.toFixed(2)}
                </strong>
              </div>
            </div>
            <p>
              Includes recorded human corrections. Review duration is not measured in this version.
            </p>
          </section>
        </div>
      </div>
    </>
  );
}

export function SettingsPage() {
  const [data, setData] = useState<{ [key: string]: unknown } | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    api<{ [key: string]: unknown }>('/settings')
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);
  if (!data) return error ? <div className="error-banner">{error}</div> : <Loading />;
  const settings = [
    ['Document extraction', String(data.extraction)],
    ['Language', 'English'],
    ['Supported documents', 'PDF, PNG, JPEG, UTF-8 TXT'],
    ['File limit', `${data.max_file_size_mb} MB · ${data.max_pages} pages per document`],
    ['Matching method', 'Exact normalized item codes'],
    ['Arithmetic', 'Decimal values · amounts rounded to cents'],
    ['Reconciliation rules', String(data.rules)],
    ['Audit history', 'Append-only events · original values preserved'],
  ];
  return (
    <div className="settings-grid">
      <section className="content-card settings-card">
        <div className="card-heading">
          <div>
            <h2>Workspace configuration</h2>
            <p>The current configuration used to process your documents.</p>
          </div>
          <Settings2 size={19} />
        </div>
        <div className="settings-rows">
          {settings.map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </section>
      <div className="settings-side">
        <section className="content-card provider-card">
          <span className="metric-icon">
            <Sparkles size={21} />
          </span>
          <h2>Multimodal extraction</h2>
          <span className="subtle-badge">
            {data.ai_key_configured ? 'Key configured' : 'Not connected'}
          </span>
          <p>
            Local extraction works without an API key. An optional Gemini connection can help read
            more varied layouts; uncertain source matches still go to review.
          </p>
          <p className="provider-hint">
            Enable the provider using the secure environment configuration described in the project
            README.
          </p>
        </section>
        <section className="content-card workspace-info">
          <ShieldCheck size={23} />
          <h3>A workspace for the first mile.</h3>
          <p>
            This single-user demo stores files and records locally. Authentication, team
            permissions, and production storage are the next steps before deployment.
          </p>
          <a className="button" href={apiUrl('/samples')}>
            <Download size={14} />
            Get sample documents
          </a>
        </section>
      </div>
    </div>
  );
}

export function OverviewPage({ cases, upload }: { cases: Case[]; upload: () => void }) {
  const total = cases.length || 1;
  const groups = [
    {
      name: 'Matched & approved',
      count: cases.filter((c) => ['matched', 'approved'].includes(c.status)).length,
      color: '#6d987d',
    },
    {
      name: 'Needs review',
      count: cases.filter((c) => ['needs_review', 'failed'].includes(c.status)).length,
      color: '#e6b768',
    },
    {
      name: 'Duplicates',
      count: cases.filter((c) => c.status === 'duplicate').length,
      color: '#df918b',
    },
    {
      name: 'Processing & rejected',
      count: cases.filter((c) => ['processing', 'rejected'].includes(c.status)).length,
      color: '#acb4be',
    },
  ];
  return (
    <>
      <div className="overview-grid">
        <section className="content-card workflow-overview">
          <span className="eyebrow">A WORKFLOW THAT ADDS UP</span>
          <h2>
            Good decisions begin
            <br />
            with connected evidence.
          </h2>
          <p>
            Follow every invoice from the first upload to the final review, with every source and
            correction in view.
          </p>
          <div className="workflow-steps">
            {[
              [UploadCloud, 'Upload'],
              [FileText, 'Extract'],
              [ShieldCheck, 'Reconcile'],
              [CheckCircle2, 'Review'],
            ].map(([Icon, label], i) => {
              const Component = Icon as typeof Check;
              return (
                <div key={String(label)}>
                  <span>
                    <Component size={19} />
                  </span>
                  <strong>{String(label)}</strong>
                  {i < 3 && <ChevronRight size={15} />}
                </div>
              );
            })}
          </div>
          <button className="button button-dark" onClick={upload}>
            Start a reconciliation <ArrowRight size={15} />
          </button>
        </section>
        <section className="content-card health-overview">
          <div className="card-heading">
            <h2>Reconciliation health</h2>
            <span className="subtle-badge">All time</span>
          </div>
          <div className="health-bar">
            {groups
              .filter((g) => g.count)
              .map((group) => (
                <span
                  key={group.name}
                  style={{ width: `${(group.count / total) * 100}%`, background: group.color }}
                />
              ))}
          </div>
          <div className="health-groups">
            {groups.map((group) => (
              <div key={group.name}>
                <span style={{ background: group.color }} />
                <strong>{group.name}</strong>
                <b>{group.count}</b>
                <small>{Math.round((group.count / total) * 100)}%</small>
              </div>
            ))}
          </div>
          <a href="#review" className="health-link">
            Take a look at the review queue <ArrowUpRight size={15} />
          </a>
        </section>
      </div>
      <section className="content-card overview-recent">
        <div className="card-heading">
          <div>
            <h2>Recent reconciliations</h2>
            <p>Your latest document sets, at a glance.</p>
          </div>
          <a href="#reconciliations">
            View all <ArrowRight size={14} />
          </a>
        </div>
        {cases.slice(0, 5).map((c) => (
          <button className="recent-row" key={c.id} onClick={() => navigate(`case/${c.id}`)}>
            <FileIcon />
            <div>
              <strong>{c.invoice?.number ?? c.filename}</strong>
              <span>{c.invoice?.supplier ?? 'Processing'}</span>
            </div>
            <span className="recent-amount">
              {c.invoice ? money(c.invoice.total, c.invoice.currency) : '—'}
            </span>
            <StatusBadge status={c.status} />
            <ArrowUpRight size={16} />
          </button>
        ))}
      </section>
    </>
  );
}
