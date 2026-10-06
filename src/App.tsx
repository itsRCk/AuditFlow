import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Separator } from '@/components/ui/separator';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useTheme } from './theme';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import {
  Activity,
  ArrowDown,
  ArrowDownToLine,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Files,
  LayoutDashboard,
  ListFilter,
  Menu,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Sun,
  Moon,
  X,
} from 'lucide-react';
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, apiUrl, date, money, navigate } from './api';
import type { Case } from './types';
import {
  Empty,
  FileIcon,
  Loading,
  Modal,
  StatusBadge,
  Toast,
  SearchField,
  SummaryCard,
} from './ui';
const UploadDialog = lazy(() => import('./UploadDialog'));
const CaseDetail = lazy(() => import('./CaseDetail'));
const ActivityPage = lazy(() =>
  import('./Pages').then((module) => ({ default: module.ActivityPage })),
);
const DocumentsPage = lazy(() =>
  import('./Pages').then((module) => ({ default: module.DocumentsPage })),
);
const MetricsPage = lazy(() =>
  import('./Pages').then((module) => ({ default: module.MetricsPage })),
);
const OverviewPage = lazy(() =>
  import('./Pages').then((module) => ({ default: module.OverviewPage })),
);
const SettingsPage = lazy(() =>
  import('./Pages').then((module) => ({ default: module.SettingsPage })),
);

const nav = [
  { id: 'overview', name: 'Overview', icon: LayoutDashboard },
  { id: 'reconciliations', name: 'Reconciliations', icon: CheckCheck },
  { id: 'review', name: 'Review queue', icon: ListFilter },
  { id: 'documents', name: 'Documents', icon: Files },
  { id: 'activity', name: 'Audit history', icon: Activity },
  { id: 'metrics', name: 'Performance', icon: ArrowUpRight },
];
const pending = (c: Case) => ['needs_review', 'duplicate', 'failed'].includes(c.status);

function Stats({ cases }: { cases: Case[] }) {
  const matched = cases.filter((c) => ['matched', 'approved'].includes(c.status)).length;
  const review = cases.filter(pending).length;
  const exposure = cases
    .filter((c) => pending(c) && c.invoice?.currency === 'USD')
    .reduce((total, c) => total + Number(c.result?.exposure || 0), 0);
  return (
    <div className="stats-grid">
      <SummaryCard
        label="Total invoices"
        value={cases.length}
        caption="Across all reconciliation cases"
        icon={Files}
      />
      <SummaryCard
        label="Matched & approved"
        value={matched}
        caption="All three documents agree"
        icon={CheckCheck}
        detail={
          <Badge variant="secondary">
            {cases.length ? Math.round((matched / cases.length) * 100) : 0}% of total
          </Badge>
        }
      />
      <SummaryCard
        label="Needs your attention"
        value={review}
        caption="Discrepancies waiting for a decision"
        icon={ListFilter}
        detail={
          <Button
            type="button"
            variant="link"
            className="h-auto p-0 text-[length:calc(var(--typeset-body-size)*0.875)]"
            onClick={() => navigate('review')}
          >
            Review queue <ArrowUpRight size={14} />
          </Button>
        }
      />
      <SummaryCard
        label="Amount flagged · USD"
        value={money(exposure)}
        caption="Potential discrepancies in open cases"
        icon={ShieldCheck}
      />
    </div>
  );
}

function Hero({ upload }: { upload: () => void }) {
  return (
    <div className="intro-banner">
      <div className="intro-copy">
        <div className="intro-label">
          <Sparkles size={13} />
          THREE-WAY MATCHING, SIMPLIFIED
        </div>
        <h2>Three documents. One clear answer.</h2>
        <p>
          Match invoices to purchase orders and deliveries.
          <br className="desktop-break" /> Catch the differences before they become problems.
        </p>
        <Button type="button" variant="secondary" className="not-typeset" onClick={upload}>
          Start a reconciliation <ArrowRight size={15} />
        </Button>
      </div>
      <div className="document-art not-typeset" aria-hidden="true">
        <div className="art-track" />
        <div className="mini-document mini-po">
          <span className="mini-icon">
            <FileIcon kind="purchase_order" small />
          </span>
          <strong>Purchase order</strong>
          <i />
          <i />
          <i className="short" />
          <div className="mini-lines">
            <b />
            <b />
            <b />
          </div>
          <span className="mini-document-label">ORDERED</span>
        </div>
        <span className="art-connector first">
          <Check size={12} />
        </span>
        <div className="mini-document mini-invoice">
          <span className="mini-icon">
            <FileIcon small />
          </span>
          <strong>Invoice</strong>
          <i />
          <i />
          <i className="short" />
          <div className="mini-lines">
            <b />
            <b />
            <b />
          </div>
          <span className="mini-document-label">INVOICED</span>
        </div>
        <span className="art-connector second">
          <Check size={12} />
        </span>
        <div className="mini-document mini-delivery">
          <span className="mini-icon">
            <FileIcon kind="delivery" small />
          </span>
          <strong>Delivery record</strong>
          <i />
          <i />
          <i className="short" />
          <div className="mini-lines">
            <b />
            <b />
            <b />
          </div>
          <span className="mini-document-label">RECEIVED</span>
        </div>
        <span className="art-verified">
          <CheckCheck size={14} />
          Everything, connected.
        </span>
      </div>
    </div>
  );
}

function CaseTable({
  cases,
  review,
  searchRef,
  upload,
}: {
  cases: Case[];
  review: boolean;
  searchRef: React.RefObject<HTMLInputElement | null>;
  upload: () => void;
}) {
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState('all');
  const [sort, setSort] = useState({ key: 'created_at', ascending: false });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(1);
  const [datesOpen, setDatesOpen] = useState(false);
  const [range, setRange] = useState({ from: '', to: '' });
  const [draft, setDraft] = useState(range);
  useEffect(() => {
    setTab('all');
    setPage(1);
    setSelected(new Set());
  }, [review]);
  useEffect(() => {
    setPage(1);
  }, [query, tab, range, sort]);
  const relevant = review ? cases.filter(pending) : cases;
  const counts = {
    all: relevant.length,
    needs_review: relevant.filter((c) => c.status === 'needs_review' || c.status === 'failed')
      .length,
    matched: relevant.filter((c) => ['matched', 'approved'].includes(c.status)).length,
    duplicate: relevant.filter((c) => c.status === 'duplicate').length,
  };
  const filtered = useMemo(
    () =>
      relevant
        .filter((c) => {
          if (tab === 'needs_review' && !['needs_review', 'failed'].includes(c.status))
            return false;
          if (tab === 'matched' && !['matched', 'approved'].includes(c.status)) return false;
          if (tab === 'duplicate' && c.status !== 'duplicate') return false;
          const haystack =
            `${c.invoice?.number} ${c.invoice?.supplier} ${c.invoice?.po_number} ${c.filename} ${c.id}`.toLowerCase();
          if (!haystack.includes(query.toLowerCase())) return false;
          const received = c.created_at.slice(0, 10);
          if ((range.from && received < range.from) || (range.to && received > range.to))
            return false;
          return true;
        })
        .sort((a, b) => {
          const value = (c: Case) =>
            sort.key === 'amount'
              ? Number(c.invoice?.total || 0)
              : sort.key === 'supplier'
                ? c.invoice?.supplier || ''
                : sort.key === 'number'
                  ? c.invoice?.number || ''
                  : c.created_at;
          const av = value(a),
            bv = value(b);
          const result =
            typeof av === 'number' && typeof bv === 'number'
              ? av - bv
              : String(av).localeCompare(String(bv));
          return sort.ascending ? result : -result;
        }),
    [cases, review, query, tab, sort, range],
  );
  const pages = Math.max(1, Math.ceil(filtered.length / 8));
  const currentPage = Math.min(page, pages);
  const visible = filtered.slice((currentPage - 1) * 8, currentPage * 8);
  const allSelected = visible.length > 0 && visible.every((c) => selected.has(c.id));
  function toggle(id: string) {
    setSelected((old) => {
      const next = new Set(old);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
  function changeSort(key: string) {
    setSort((old) => ({ key, ascending: old.key === key ? !old.ascending : true }));
  }
  function exportSelected() {
    const safe = (value: unknown) => {
      const text = String(value ?? '');
      return `"${(/^[=+@\-\t\r]/.test(text) ? "'" : '') + text.replaceAll('"', '""')}"`;
    };
    const rows = [
      ['Invoice', 'Supplier', 'PO', 'Currency', 'Total', 'Status'],
      ...cases
        .filter((c) => selected.has(c.id))
        .map((c) => [
          c.invoice?.number,
          c.invoice?.supplier,
          c.invoice?.po_number,
          c.invoice?.currency,
          c.invoice?.total,
          c.status,
        ]),
    ];
    const url = URL.createObjectURL(
      new Blob([rows.map((row) => row.map(safe).join(',')).join('\r\n')], { type: 'text/csv' }),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'auditflow-selected.csv';
    anchor.click();
    URL.revokeObjectURL(url);
  }
  const SortIcon = sort.ascending ? ArrowUp : ArrowDown;
  return (
    <Tabs value={tab} onValueChange={setTab} className="table-section block">
      <div className="table-heading">
        <div>
          <h2>
            {review ? 'Your review queue' : 'All reconciliations'}
            <span className="count-badge">{relevant.length}</span>
          </h2>
          <p>
            {review
              ? 'Check the evidence, correct values, and record a decision.'
              : 'A complete picture of every invoice, from upload to approval.'}
          </p>
        </div>
        <div className="table-heading-actions">
          {selected.size ? (
            <Button variant="outline" type="button" className="button" onClick={exportSelected}>
              <ArrowDownToLine size={14} />
              Export {selected.size} selected
            </Button>
          ) : (
            <Button asChild variant="outline">
              <a className="button" href={apiUrl('/export')}>
                <ArrowDownToLine size={14} />
                Export
              </a>
            </Button>
          )}
        </div>
      </div>
      <div className="table-controls">
        <TabsList variant="default" className="table-tabs" aria-label="Reconciliation status">
          {(['all', 'needs_review', 'matched', 'duplicate'] as const)
            .filter((t) => !(review && t === 'matched'))
            .map((t) => (
              <TabsTrigger value={t} key={t}>
                {
                  {
                    all: 'All invoices',
                    needs_review: 'Needs review',
                    matched: 'Matched',
                    duplicate: 'Duplicates',
                  }[t]
                }
                <span>{counts[t]}</span>
              </TabsTrigger>
            ))}
        </TabsList>
        <div className="table-filters">
          <SearchField
            ref={searchRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onClear={() => setQuery('')}
            placeholder="Search invoices…"
            aria-label="Search invoices"
          />
          <Popover open={datesOpen} onOpenChange={setDatesOpen}>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                type="button"
                className={`button filter-button ${range.from || range.to ? 'filter-active' : ''}`}
                onClick={() => {
                  setDraft(range);
                }}
              >
                <CalendarDays size={14} />
                {range.from || range.to ? 'Date range' : 'All time'}
                <ChevronDown size={12} />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="date-popover static w-72">
              <strong>Filter by upload date</strong>
              <label>
                From
                <Input
                  type="date"
                  value={draft.from}
                  onChange={(e) => setDraft({ ...draft, from: e.target.value })}
                />
              </label>
              <label>
                To
                <Input
                  type="date"
                  value={draft.to}
                  min={draft.from}
                  onChange={(e) => setDraft({ ...draft, to: e.target.value })}
                />
              </label>
              <div>
                <Button
                  variant="outline"
                  type="button"
                  className="button"
                  onClick={() => {
                    setRange({ from: '', to: '' });
                    setDatesOpen(false);
                  }}
                >
                  Clear
                </Button>
                <Button
                  variant="default"
                  type="button"
                  className="button button-dark"
                  disabled={!!(draft.from && draft.to && draft.from > draft.to)}
                  onClick={() => {
                    setRange(draft);
                    setDatesOpen(false);
                  }}
                >
                  Apply
                </Button>
              </div>
            </PopoverContent>
          </Popover>
        </div>
      </div>
      <TabsContent value={tab} className="mt-0">
        {visible.length ? (
          <div className="table-scroll">
            <table className="cases-table">
              <thead>
                <tr>
                  <th className="checkbox-cell">
                    <Checkbox
                      aria-label="Select visible invoices"
                      checked={allSelected}
                      onCheckedChange={() =>
                        setSelected((old) => {
                          const next = new Set(old);
                          visible.forEach((c) =>
                            allSelected ? next.delete(c.id) : next.add(c.id),
                          );
                          return next;
                        })
                      }
                    />
                  </th>
                  <th>
                    <button onClick={() => changeSort('number')}>
                      Invoice{' '}
                      {sort.key === 'number' ? <SortIcon size={12} /> : <ChevronDown size={12} />}
                    </button>
                  </th>
                  <th>
                    <button onClick={() => changeSort('supplier')}>
                      Supplier {sort.key === 'supplier' && <SortIcon size={12} />}
                    </button>
                  </th>
                  <th>Purchase order</th>
                  <th className="amount-cell">
                    <button onClick={() => changeSort('amount')}>
                      Amount {sort.key === 'amount' && <SortIcon size={12} />}
                    </button>
                  </th>
                  <th>Status</th>
                  <th>
                    <button onClick={() => changeSort('created_at')}>
                      Received {sort.key === 'created_at' && <SortIcon size={12} />}
                    </button>
                  </th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((c) => (
                  <tr
                    key={c.id}
                    className={selected.has(c.id) ? 'selected' : ''}
                    onClick={() => navigate(`case/${c.id}`)}
                  >
                    <td className="checkbox-cell" onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        aria-label={`Select ${c.invoice?.number ?? c.filename}`}
                        checked={selected.has(c.id)}
                        onCheckedChange={() => toggle(c.id)}
                      />
                    </td>
                    <td>
                      <button className="invoice-cell" onClick={() => navigate(`case/${c.id}`)}>
                        <FileIcon />
                        <span>
                          <strong>{c.invoice?.number ?? c.filename}</strong>
                          <small className="mobile-supplier">
                            {c.invoice?.supplier ?? 'Processing documents'}
                          </small>
                          <small>
                            {c.document_count} documents{c.is_demo ? ' · Sample' : ''}
                          </small>
                        </span>
                      </button>
                    </td>
                    <td className="supplier-cell">
                      {c.invoice?.supplier ?? <span className="muted">Awaiting extraction</span>}
                    </td>
                    <td>
                      <span className="po-label">{c.invoice?.po_number ?? '—'}</span>
                    </td>
                    <td className="amount-cell">
                      {c.invoice ? money(c.invoice.total, c.invoice.currency) : '—'}
                    </td>
                    <td>
                      <StatusBadge status={c.status} />
                    </td>
                    <td className="date-cell">
                      {date(c.created_at, { day: '2-digit', month: 'short' })}
                    </td>
                    <td>
                      <button
                        className="row-arrow"
                        aria-label={`Open ${c.invoice?.number ?? c.filename}`}
                      >
                        <ArrowUpRight size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={query || range.from || range.to ? 'No invoices found' : 'You’re all caught up'}
            action={
              relevant.length ? (
                <Button
                  variant="outline"
                  type="button"
                  className="button"
                  onClick={() => {
                    setQuery('');
                    setTab('all');
                    setRange({ from: '', to: '' });
                  }}
                >
                  Clear filters
                </Button>
              ) : (
                <Button
                  variant="default"
                  type="button"
                  className="button button-primary"
                  onClick={upload}
                >
                  <Plus size={15} />
                  New reconciliation
                </Button>
              )
            }
          >
            {query
              ? 'Try another invoice number, supplier, or purchase order.'
              : 'Upload a document set to start a new reconciliation.'}
          </Empty>
        )}
        <div className="table-footer">
          <span>
            {filtered.length
              ? `Showing ${(currentPage - 1) * 8 + 1}–${Math.min(currentPage * 8, filtered.length)} of ${filtered.length} invoices`
              : '0 invoices'}
            {selected.size ? ` · ${selected.size} selected` : ''}
          </span>
          <div>
            <Button
              variant="outline"
              type="button"
              className="button pagination-button"
              disabled={currentPage <= 1}
              onClick={() => setPage(currentPage - 1)}
            >
              <ChevronLeft size={14} />
              Previous
            </Button>
            <button className="page-number" aria-label={`Page ${currentPage}`}>
              {currentPage}
            </button>
            <Button
              variant="outline"
              type="button"
              className="button pagination-button"
              disabled={currentPage >= pages}
              onClick={() => setPage(currentPage + 1)}
            >
              Next
              <ChevronRight size={14} />
            </Button>
          </div>
        </div>
      </TabsContent>
    </Tabs>
  );
}

export default function App() {
  const { theme, toggleTheme } = useTheme();
  const [route, setRoute] = useState(window.location.hash.slice(1) || 'reconciliations');
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [uploadOpen, setUploadOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [connected, setConnected] = useState(false);
  const [toast, setToast] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeUpload = useCallback(() => setUploadOpen(false), []);
  const closeHelp = useCallback(() => setHelpOpen(false), []);
  const notify = useCallback((message: string) => {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(''), 4200);
  }, []);
  const refresh = useCallback(async () => {
    try {
      const data = await api<Case[]>('/cases');
      setCases(data);
      setError('');
      const health = await api<{ worker_alive: boolean }>('/health');
      setConnected(health.worker_alive);
    } catch (error) {
      setError((error as Error).message);
      setConnected(false);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    const listener = () => {
      setRoute(window.location.hash.slice(1) || 'reconciliations');
      setMobileOpen(false);
    };
    window.addEventListener('hashchange', listener);
    refresh();
    const timer = setInterval(refresh, 2500);
    const key = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
        event.preventDefault();
        navigate('reconciliations');
        setTimeout(() => searchRef.current?.focus(), 50);
      }
    };
    document.addEventListener('keydown', key);
    return () => {
      window.removeEventListener('hashchange', listener);
      clearInterval(timer);
      document.removeEventListener('keydown', key);
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, [refresh]);
  const isCase = route.startsWith('case/');
  const page = isCase ? 'reconciliations' : route;
  const pageName =
    nav.find((n) => n.id === page)?.name ??
    (page === 'settings' ? 'Workspace settings' : 'Reconciliations');
  const reviewCount = cases.filter(pending).length;
  return (
    <div className="app-shell">
      {mobileOpen && <div className="sidebar-backdrop" onClick={() => setMobileOpen(false)} />}
      <aside className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
        <a className="brand" href="#reconciliations">
          <span className="brand-symbol">
            <ArrowRight size={20} />
            <ArrowRight size={20} />
          </span>
          AuditFlow<span className="brand-dot">.</span>
        </a>
        <div className="workspace-switch">
          <span className="workspace-icon">A</span>
          <div>
            <strong>Finance workspace</strong>
            <span>Team workspace</span>
          </div>
          <span className="workspace-dot" />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {nav.map(({ id, name, icon: Icon }) => (
            <a
              key={id}
              href={`#${id}`}
              className={`nav-link ${page === id ? 'active' : ''}`}
              aria-current={page === id ? 'page' : undefined}
            >
              <Icon size={18} strokeWidth={1.65} />
              <span>{name}</span>
              {id === 'review' && reviewCount > 0 && <b>{reviewCount}</b>}
              {page === id && id !== 'review' && <span className="active-dot" />}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-tip">
            <span className="tip-icon">
              <ShieldCheck size={20} strokeWidth={1.5} />
            </span>
            <strong>Confidence in every line.</strong>
            <p>
              Every value has a source.
              <br />
              Every decision leaves a trail.
            </p>
            <button onClick={() => setHelpOpen(true)}>
              Explore the workflow <ArrowUpRight size={13} />
            </button>
          </div>
          <a
            href="#settings"
            className={`nav-link settings-link ${page === 'settings' ? 'active' : ''}`}
          >
            <Settings2 size={17} strokeWidth={1.6} />
            Workspace settings
          </a>
          <div className="sidebar-user">
            <span className="avatar">AR</span>
            <div>
              <strong>Alex Rivera</strong>
              <span>Demo reviewer</span>
            </div>
            <span className="user-indicator" />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <Button
              variant="ghost"
              size="icon"
              type="button"
              className="icon-button mobile-menu hidden max-[1024px]:inline-flex"
              aria-label="Open navigation"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={20} />
            </Button>
            <span>Workspace</span>
            <ChevronRight size={12} />
            <strong>{isCase ? 'Invoice detail' : pageName}</strong>
          </div>
          <div className="topbar-right">
            <button
              className="quick-search"
              onClick={() => {
                navigate('reconciliations');
                setTimeout(() => searchRef.current?.focus(), 50);
              }}
            >
              <Search size={15} />
              <span>Quick search</span>
              <kbd>⌘ K</kbd>
            </button>
            <Separator orientation="vertical" className="topbar-divider h-5" />
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  type="button"
                  aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}
                  onClick={toggleTheme}
                >
                  {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
                </Button>
              </TooltipTrigger>
              <TooltipContent>{theme === 'light' ? 'Dark' : 'Light'} theme</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  type="button"
                  className="icon-button help-button"
                  aria-label="Open workflow guide"
                  onClick={() => setHelpOpen(true)}
                >
                  <CircleHelp size={18} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Workflow guide</TooltipContent>
            </Tooltip>
            <span className="avatar small-avatar" title="Demo reviewer Alex Rivera">
              AR
            </span>
          </div>
        </header>
        <main className={`main-content ${isCase ? 'detail-main' : ''}`}>
          {error && (
            <div className="error-banner" role="alert">
              {error}
              <button onClick={refresh}>Retry</button>
            </div>
          )}
          <Suspense fallback={<Loading />}>
            {isCase ? (
              <CaseDetail id={route.split('/')[1]} changed={refresh} notify={notify} />
            ) : (
              <>
                <div className="page-heading">
                  <div>
                    <div className="heading-eyebrow">
                      {page === 'review'
                        ? 'HUMAN INSIGHT, WHERE IT MATTERS'
                        : page === 'reconciliations'
                          ? 'LESS CHECKING. MORE CERTAINTY.'
                          : 'YOUR FINANCE WORKSPACE'}
                    </div>
                    <h1>
                      {pageName}
                      <span className="heading-dot">.</span>
                    </h1>
                    <p>
                      {
                        (
                          {
                            overview: 'Everything you need to know, all in one place.',
                            reconciliations:
                              'Bring your documents together. Keep your numbers in sync.',
                            review: 'A little attention now. A lot of confidence later.',
                            documents: 'Your source of truth, organized and always within reach.',
                            activity: 'A traceable history of every change and decision.',
                            metrics: 'Measure what matters. Improve with evidence.',
                            settings: 'A clear view of how your workspace is configured.',
                          } as { [key: string]: string }
                        )[page]
                      }
                    </p>
                  </div>
                  <Button
                    variant="default"
                    type="button"
                    className="button button-primary new-button"
                    onClick={() => setUploadOpen(true)}
                  >
                    <Plus size={17} />
                    New reconciliation
                  </Button>
                </div>
                {loading ? (
                  <Loading />
                ) : page === 'reconciliations' || page === 'review' ? (
                  <>
                    <Stats cases={cases} />
                    {page === 'reconciliations' && <Hero upload={() => setUploadOpen(true)} />}
                    {page === 'review' && (
                      <div className="review-intro">
                        <ShieldCheck size={20} />
                        <div>
                          <strong>Your judgment completes the picture.</strong>
                          <p>
                            Inspect the source, make a correction, or acknowledge a discrepancy.
                            Your decision is saved in the audit history.
                          </p>
                        </div>
                      </div>
                    )}
                    <CaseTable
                      cases={cases}
                      review={page === 'review'}
                      searchRef={searchRef}
                      upload={() => setUploadOpen(true)}
                    />
                  </>
                ) : page === 'overview' ? (
                  <>
                    <Stats cases={cases} />
                    <OverviewPage cases={cases} upload={() => setUploadOpen(true)} />
                  </>
                ) : page === 'documents' ? (
                  <DocumentsPage />
                ) : page === 'activity' ? (
                  <ActivityPage cases={cases} />
                ) : page === 'metrics' ? (
                  <MetricsPage />
                ) : page === 'settings' ? (
                  <SettingsPage />
                ) : (
                  <Empty
                    title="Page not found"
                    action={
                      <Button asChild variant="outline">
                        <a href="#reconciliations" className="button">
                          Back to reconciliations
                        </a>
                      </Button>
                    }
                  >
                    Choose a page from your workspace.
                  </Empty>
                )}
                <div className="workspace-footer">
                  <span>
                    <span className={`connection-dot ${connected ? 'online' : ''}`} />
                    {connected ? 'Workspace connected' : 'Connecting to workspace'}
                  </span>
                  <span>
                    <ShieldCheck size={12} />
                    Traceable from source to decision
                  </span>
                  <span>AuditFlow v0.1</span>
                </div>
              </>
            )}
          </Suspense>
        </main>
      </div>
      <Suspense fallback={null}>
        {uploadOpen && (
          <UploadDialog
            close={closeUpload}
            done={(id, created) => {
              closeUpload();
              refresh();
              navigate(`case/${id}`);
              notify(
                created
                  ? 'Documents uploaded. Your reconciliation is processing.'
                  : 'This packet already exists. Opening the original case.',
              );
            }}
          />
        )}
      </Suspense>
      {helpOpen && (
        <Modal close={closeHelp} label="Workflow guide">
          <div className="modal-header">
            <div>
              <span className="eyebrow">A CLEARER WAY TO RECONCILE</span>
              <h2>From documents to decisions.</h2>
              <p>Three-way matching, with the evidence always close by.</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              type="button"
              className="icon-button"
              aria-label="Close workflow guide"
              onClick={closeHelp}
            >
              <X size={20} />
            </Button>
          </div>
          <div className="guide-body">
            {[
              [
                '01',
                'Upload a document set',
                'Add the invoice, its purchase order, and the delivery record. English PDF, image, and text documents are supported.',
              ],
              [
                '02',
                'Follow every number to its source',
                'Open a case and click any extracted value. The original document highlights the exact location.',
              ],
              [
                '03',
                'Resolve the differences',
                'Check quantities, prices, totals, and duplicates. Correct a field with a reason or record an approval or rejection.',
              ],
              [
                '04',
                'Take the evidence with you',
                'Export a case with original values, corrections, source locations, and an immutable audit history.',
              ],
            ].map(([step, title, content]) => (
              <div className="guide-step" key={step}>
                <span>{step}</span>
                <div>
                  <h3>{title}</h3>
                  <p>{content}</p>
                </div>
              </div>
            ))}
            <Button asChild variant="outline">
              <a className="button" href={apiUrl('/samples')}>
                <ArrowDownToLine size={15} />
                Download the sample documents
              </a>
            </Button>
            <p className="demo-disclaimer">
              This is a single-user demo. Suppliers, reviewers, and transactions in the sample
              workspace are fictional.
            </p>
          </div>
          <div className="modal-footer">
            <Button
              variant="default"
              type="button"
              className="button button-primary"
              onClick={closeHelp}
            >
              Got it <Check size={16} />
            </Button>
          </div>
        </Modal>
      )}
      {toast && <Toast message={toast} />}
    </div>
  );
}
