import type { IncomingMessage, ServerResponse } from 'node:http';

export async function readBody(request: IncomingMessage): Promise<Buffer> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.length;
    if (size > 64 * 1024) throw new Error('Request body is too large.');
    chunks.push(buffer);
  }
  return Buffer.concat(chunks);
}

export async function readJson(request: IncomingMessage): Promise<unknown> {
  return JSON.parse((await readBody(request)).toString('utf8'));
}

export function reply(response: ServerResponse, status: number, body?: unknown) {
  response.statusCode = status;
  if (body === undefined) return response.end();
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  return response.end(JSON.stringify(body));
}
