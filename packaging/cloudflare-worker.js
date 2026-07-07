// Cloudflare Worker for getresearcher.auspexai.network
//
// Proxies the researcher install script from GitHub instead of redirecting,
// so there's no CDN caching staleness. Mirrors getworker.auspexai.network.
// Deploy via the Workers & Pages dashboard (or `wrangler deploy`, see
// wrangler.toml) and bind the custom domain getresearcher.auspexai.network.

const SCRIPT_URL =
  "https://raw.githubusercontent.com/auspexai/researcher-dashboard/main/install.sh";

export default {
  async fetch() {
    // Cache-bust the upstream fetch with a unique query per request AND disable
    // the edge cache, so neither Cloudflare's cache nor GitHub raw's branch CDN
    // can serve a stale install.sh — a push to main is live IMMEDIATELY, not
    // after a TTL. (Installer traffic is low; skipping the cache costs nothing,
    // and a stale installer showing an old version number is the worse failure.)
    const upstream = await fetch(`${SCRIPT_URL}?_cb=${Date.now()}`, {
      cf: { cacheTtl: 0 },
    });

    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store, max-age=0",
      },
    });
  },
};
