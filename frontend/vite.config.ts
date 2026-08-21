import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { defineConfig } from 'vite';

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
