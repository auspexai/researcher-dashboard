import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		// Static export: the FastAPI backend serves the built bundle. No SSR;
		// the dashboard fetches tenant-scoped data from its own local backend,
		// which signs coordinator requests with the researcher's SDK key
		// (researcher_dashboard_design.md §4/§5).
		adapter: adapter({
			fallback: 'index.html', // SPA fallback for client-side routing
			pages: 'build',
			assets: 'build',
			precompress: false,
			strict: true
		}),
		prerender: {
			handleHttpError: 'warn'
		}
	}
};

export default config;
