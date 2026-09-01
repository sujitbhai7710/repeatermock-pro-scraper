// RepeaterMock PRO Scraper — Dashboard Worker (cron trigger only, no D1)
// Triggers GitHub Actions scrape.yml every 15 minutes to keep tokens alive

export default {
  async fetch(req, env) {
    const url = new URL(req.url);

    // Simple health check
    if (url.pathname === '/' || url.pathname === '/health') {
      return new Response(JSON.stringify({
        status: 'ok',
        worker: 'repeatermock-pro-cron',
        cron: 'every 15 min → triggers scrape.yml',
        dashboard: 'https://sujitbhai7710.github.io/repeatermock-pro-scraper/',
        repo: env.GH_REPO || 'not configured',
      }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // Manual trigger endpoint (password protected)
    if (url.pathname === '/trigger' && req.method === 'POST') {
      const body = await req.json().catch(() => ({}));
      if (body.password !== env.ADMIN_PASSWORD) {
        return new Response(JSON.stringify({ success: false, error: 'Unauthorized' }), { status: 401 });
      }
      if (!env.GH_TOKEN || !env.GH_REPO) {
        return new Response(JSON.stringify({ success: false, error: 'GH_TOKEN or GH_REPO not set' }), { status: 500 });
      }
      try {
        const r = await fetch(
          `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/scrape.yml/dispatches`,
          {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${env.GH_TOKEN}`,
              'Accept': 'application/vnd.github+json',
              'Content-Type': 'application/json',
              'User-Agent': 'repeatermock-cron-worker',
            },
            body: JSON.stringify({ ref: 'main' }),
          }
        );
        return new Response(JSON.stringify({
          success: r.status === 204,
          status: r.status,
        }), { headers: { 'Content-Type': 'application/json' } });
      } catch (e) {
        return new Response(JSON.stringify({ success: false, error: e.message }), { status: 500 });
      }
    }

    return new Response(JSON.stringify({
      status: 'ok',
      endpoints: {
        '/': 'health check',
        '/trigger': 'POST with {password: "..."} to trigger scrape manually',
      },
      dashboard: 'https://sujitbhai7710.github.io/repeatermock-pro-scraper/',
    }), { headers: { 'Content-Type': 'application/json' } });
  },

  // Cron: every 15 minutes → trigger GitHub Actions scrape.yml
  // This keeps the refresh token chain alive (tokens rotate every 8 tests)
  // Even if no tests are pending, the scraper will just exit quickly
  async scheduled(event, env, ctx) {
    if (!env.GH_TOKEN || !env.GH_REPO) {
      console.log('Cron: GH_TOKEN or GH_REPO not set — skipping');
      return;
    }
    try {
      const resp = await fetch(
        `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/scrape.yml/dispatches`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${env.GH_TOKEN}`,
            'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json',
            'User-Agent': 'repeatermock-cron-worker',
          },
          body: JSON.stringify({ ref: 'main' }),
        }
      );
      console.log(`Cron: triggered scrape.yml → HTTP ${resp.status} at ${new Date().toISOString()}`);
    } catch (e) {
      console.error('Cron: failed to trigger:', e.message);
    }
  },
};
