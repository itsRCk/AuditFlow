import { timingSafeEqual } from 'node:crypto';
import { send } from '@vercel/queue';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { readJson, reply } from './http';

export default async function handler(request: IncomingMessage, response: ServerResponse) {
  const token = process.env.AUDITFLOW_JOB_TOKEN;
  const received = Buffer.from(request.headers.authorization ?? '');
  const expected = Buffer.from(`Bearer ${token ?? ''}`);
  if (!token || received.length !== expected.length || !timingSafeEqual(received, expected)) {
    return reply(response, 404, { detail: 'Unknown API endpoint.' });
  }
  if (request.method !== 'POST') return reply(response, 405);
  let caseId: unknown;
  try {
    const body = (await readJson(request)) as { case_id?: unknown } | null;
    caseId = body?.case_id;
  } catch {
    return reply(response, 422, { detail: 'Invalid job identifier.' });
  }
  if (typeof caseId !== 'string' || !/^[a-f0-9]{32}$/.test(caseId)) {
    return reply(response, 422, { detail: 'Invalid job identifier.' });
  }
  try {
    await send('auditflow-documents', { case_id: caseId });
    return reply(response, 202, { id: caseId });
  } catch {
    return reply(response, 503, { detail: 'Document processing is temporarily unavailable.' });
  }
}
