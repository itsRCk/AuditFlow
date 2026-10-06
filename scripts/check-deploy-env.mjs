const value = process.env.VITE_API_BASE_URL?.trim();
if (!value) {
  // The Vercel Services deployment routes the API on this same origin.
  process.exit(0);
}
try {
  const parsed = new URL(value);
  if (
    parsed.protocol !== 'https:' ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    (parsed.pathname !== '/' && parsed.pathname !== '')
  ) {
    throw new Error('Use an HTTPS origin without a path, credentials, query, or fragment.');
  }
} catch {
  console.error(
    'VITE_API_BASE_URL must be an HTTPS backend origin, for example https://api.your-domain.com.',
  );
  process.exit(1);
}
