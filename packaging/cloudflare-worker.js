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
    const upstream = await fetch(SCRIPT_URL, {
      cf: { cacheTtl: 60, cacheEverything: true },
    });

    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "public, max-age=60",
      },
    });
  },
};
