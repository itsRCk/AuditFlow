import { QueueClient } from '@vercel/queue';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { readBody, reply } from './http';

const queue = new QueueClient();

const callback = queue.handleCallback<{ case_id: string }>(async (message) => {
  if (!/^[a-f0-9]{32}$/.test(message.case_id)) throw new Error('Invalid job identifier.');
  const origin = process.env.AUDITFLOW_PROCESSOR_URL;
  const token = process.env.AUDITFLOW_JOB_TOKEN;
  if (!origin || !token) throw new Error('Document processor is not configured.');
  const response = await fetch(
    new URL(`api/internal/jobs/${message.case_id}`, `${origin.replace(/\/$/, '')}/`),
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(280_000),
    },
  );
  if (!response.ok) throw new Error('Document processing has not completed; retry the job.');
});

export default async function handler(request: IncomingMessage, response: ServerResponse) {
  const headers = new Headers();
  for (const [name, values] of Object.entries(request.headers)) {
    if (values === undefined) continue;
    for (const value of Array.isArray(values) ? values : [values]) headers.append(name, value);
  }
  const method = request.method ?? 'GET';
  try {
    const result = await callback(
      new Request(new URL(request.url ?? '/', 'http://queue.internal'), {
        method,
        headers,
        body:
          method === 'GET' || method === 'HEAD'
            ? undefined
            : new Uint8Array(await readBody(request)),
      }),
    );
    response.statusCode = result.status;
    result.headers.forEach((value, name) => response.setHeader(name, value));
    response.end(Buffer.from(await result.arrayBuffer()));
  } catch {
    reply(response, 503, { detail: 'Document processing is temporarily unavailable.' });
  }
}
