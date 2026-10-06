import { timingSafeEqual } from 'node:crypto';
import { send } from '@vercel/queue';
import type { VercelRequest, VercelResponse } from '@vercel/node';

export default async function handler(request: VercelRequest, response: VercelResponse) {
  const token = process.env.AUDITFLOW_JOB_TOKEN;
  const received = Buffer.from(request.headers.authorization ?? '');
  const expected = Buffer.from(`Bearer ${token ?? ''}`);
  if (!token || received.length !== expected.length || !timingSafeEqual(received, expected)) {
    return response.status(404).json({ detail: 'Unknown API endpoint.' });
  }
  if (request.method !== 'POST') return response.status(405).end();
  const caseId = request.body?.case_id;
  if (typeof caseId !== 'string' || !/^[a-f0-9]{32}$/.test(caseId)) {
    return response.status(422).json({ detail: 'Invalid job identifier.' });
  }
  try {
    await send('auditflow-documents', { case_id: caseId });
    return response.status(202).json({ id: caseId });
  } catch {
    return response.status(503).json({ detail: 'Document processing is temporarily unavailable.' });
  }
}
