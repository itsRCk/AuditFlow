import { handleUpload, type HandleUploadBody } from '@vercel/blob/client';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { readJson, reply } from './http';

export default async function handler(request: IncomingMessage, response: ServerResponse) {
  if (request.method !== 'POST') return reply(response, 405);
  try {
    const result = await handleUpload({
      body: (await readJson(request)) as HandleUploadBody,
      request,
      onBeforeGenerateToken: async (pathname) => {
        if (
          !/^incoming\/[a-f0-9-]{36}\/[a-zA-Z0-9_.-]{1,180}\.(pdf|png|jpe?g|txt)$/i.test(pathname)
        ) {
          throw new Error('Invalid document upload.');
        }
        // This project is a public demonstration; issued tokens only upload
        // one bounded document to a random incoming key and cannot read files.
        return {
          allowedContentTypes: ['application/pdf', 'image/png', 'image/jpeg', 'text/plain'],
          maximumSizeInBytes: 20 * 1024 * 1024,
          validUntil: Date.now() + 5 * 60 * 1000,
          addRandomSuffix: false,
          allowOverwrite: false,
        };
      },
    });
    return reply(response, 200, result);
  } catch {
    return reply(response, 400, { detail: 'Document upload could not be authorized. Try again.' });
  }
}
