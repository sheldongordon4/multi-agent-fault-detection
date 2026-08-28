import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
// `vitest/config` re-exports Vite's defineConfig with the `test` key typed,
// so tests inherit resolve.alias instead of redeclaring it.
import { defineConfig } from 'vitest/config';

// https://vite.dev/config/
export default defineConfig({
	plugins: [react(), tailwindcss()],
	resolve: {
		alias: {
			'@': path.resolve(import.meta.dirname, './src'),
			'@app': path.resolve(import.meta.dirname, './src/app'),
			'@features': path.resolve(import.meta.dirname, './src/features'),
			'@shared': path.resolve(import.meta.dirname, './src/shared'),
		},
	},
	// Frontend reads VITE_* vars from the project root .env (shared with the backend).
	envDir: path.resolve(import.meta.dirname, '../'),
	envPrefix: 'VITE_',
	server: {
		host: true,
		port: 5173,
		

		
		watch: {
			usePolling: true,
			interval: 1000,
			ignored: [
				'**/node_modules/**',
				'**/.pnpm-store/**',
				'**/.git/**',
				'**/dist/**',
				'**/.tmp/**',
				'**/public/map/**',
			],
		},
	},
	preview: {
		port: 3000,
	},
	test: {
		// Node, not jsdom: these cover pure domain logic (severity folding,
		// filtering, recency). Component tests would need jsdom + Testing Library.
		environment: 'node',
		include: ['src/**/*.test.ts'],
	},
	build: {
		rollupOptions: {
			output: {
				manualChunks: (id) => {
					if (id.includes('@radix-ui/')) return 'radix';
				},
			},
		},
	},
});
