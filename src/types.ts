export type Status =
  | 'processing'
  | 'matched'
  | 'needs_review'
  | 'duplicate'
  | 'approved'
  | 'rejected'
  | 'failed';
export type Kind = 'invoice' | 'purchase_order' | 'delivery';
export type LineItem = {
  sku: string;
  description: string;
  quantity: string;
  unit_price: string | null;
  amount: string | null;
};
export type RecordData = {
  kind: Kind;
  supplier: string;
  number: string;
  po_number: string;
  date: string;
  currency: string;
  subtotal: string | null;
  tax: string | null;
  total: string | null;
  line_items: LineItem[];
};
export type Source = { page: number; bbox: number[]; text: string };
export type ExtractedField = {
  value: string;
  extracted_value: string;
  confidence: number;
  source: Source | null;
  corrected: boolean;
};
export type Document = {
  id: string;
  case_id: string;
  kind: Kind;
  filename: string;
  digest: string;
  size: number;
  record?: RecordData | null;
  fields?: { [path: string]: ExtractedField };
  uncertain?: string[];
  errors?: string[];
  pages?: { page: number; width: number; height: number }[];
  method?: string;
  case_status?: Status;
};
export type Flag = {
  code: string;
  title: string;
  message: string;
  severity: string;
  paths: { kind: Kind; path: string }[];
  amount?: string;
};
export type Result = {
  status: Status;
  flags: Flag[];
  lines: {
    sku: string;
    description: string;
    invoiced: string;
    ordered: string | null;
    received: string | null;
    unit_price: string;
    amount: string;
    issues: string[];
    invoice_index: number;
  }[];
  exposure: string;
  rule_version: string;
  duplicate_cases?: string[];
};
export type Job = { state: string; attempts: number; duration_ms?: number; error?: string };
export type Case = {
  id: string;
  status: Status;
  revision: number;
  created_at: string;
  is_demo: boolean;
  invoice: RecordData | null;
  result: Result | null;
  job: Job;
  filename?: string;
  document_count?: number;
  documents?: Document[];
  audit?: AuditEvent[];
};
export type AuditEvent = {
  sequence: number;
  case_id: string;
  document_id?: string;
  action: string;
  actor: string;
  payload: { [key: string]: unknown };
  created_at: string;
};
export type Evaluation = {
  dataset: string;
  layouts: number;
  documents: number;
  scanned_documents: number;
  fields_correct: number;
  fields_total: number;
  field_accuracy: number;
  discrepancy_precision: number;
  discrepancy_recall: number;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  validation_failures: number;
  scenarios: {
    scenario: string;
    supplier: string;
    expected: string[];
    observed: string[];
    passed: boolean;
  }[];
  evaluated_at: string;
  limitation: string;
};
export type Metrics = {
  documents_processed: number;
  corrections: number;
  reviewed_cases: number;
  corrections_per_reviewed_case: number | null;
  average_processing_ms: number | null;
  api_cost_usd: string | null;
  cost_per_document: string | null;
  evaluation: Evaluation | null;
};
