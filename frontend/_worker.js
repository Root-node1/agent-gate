// Cloudflare Pages SPA fallback worker.
// Serves index.html for all routes that are not static assets or API routes,
// allowing React Router to handle client-side navigation.
// API routes (/api/*, /v1/*) are excluded by _routes.json.

export async function onRequest(context) {
  const response = await fetch(new URL('/index.html', context.request.url))
  return new Response(response.body, {
    status: 200,
    headers: response.headers,
  })
}
