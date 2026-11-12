// Cloudflare Workers with Static Assets — Worker entry point.
//
// The Worker runs only for /_worker.js (configured via run_worker_first
// in wrangler.toml) to prevent the worker source from being served as a
// static file. All other requests are handled by the static assets binding
// with not_found_handling = "single-page-application", which automatically
// serves index.html for unknown routes.
//
// API requests (/api/*, /v1/*) are NOT handled here. The backend runs on a
// separate subdomain (api.agentgate.zindika.app) and the frontend API client
// uses VITE_API_BASE_URL to target it directly.

export default {
  async fetch(request) {
    return new Response("Not Found", { status: 404 });
  },
};
