import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		// Dev-only: proxy /api to the local backend so `pnpm dev` works
		// against `auspexai-dashboard serve` without CORS.
		proxy: {
			'/api': 'http://127.0.0.1:4228'
		}
	}
});
