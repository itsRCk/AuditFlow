export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, options);
  } catch {
    throw new Error('Cannot reach AuditFlow. Check the server and try again.');
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === 'string'
        ? data.detail
        : `Request failed (${response.status}). Check your input and try again.`,
    );
  }
  return response.json();
}
export const jsonRequest = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});
export const money = (value?: string | number | null, currency = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 2 }).format(
    Number(value || 0),
  );
export const date = (value: string, options?: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat(
    'en-GB',
    options ?? { day: '2-digit', month: 'short', year: 'numeric' },
  ).format(new Date(value));
export function navigate(page: string) {
  window.location.hash = page;
}
export const kindLabel = {
  invoice: 'Invoice',
  purchase_order: 'Purchase order',
  delivery: 'Delivery record',
};
export function fieldLabel(path: string) {
  const name = path.split('.').at(-1) ?? path;
  return (
    (
      {
        po_number: 'PO number',
        number: 'Document number',
        supplier: 'Supplier',
        date: 'Document date',
        currency: 'Currency',
        subtotal: 'Subtotal',
        tax: 'Tax',
        total: 'Total',
        sku: 'Item code',
        description: 'Description',
        quantity: 'Quantity',
        unit_price: 'Unit price',
        amount: 'Line total',
      } as { [key: string]: string }
    )[name] ?? name
  );
}
