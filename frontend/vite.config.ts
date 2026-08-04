import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { defineConfig } from 'vite';

// https://vite.dev/config/
export default defineConfig({
	plugins: [react(), tailwindcss()],
	resolve: {
		alias: {
			'@': path.resolve(__dirname, './src'),
			'@app': path.resolve(__dirname, './src/app'),
			'@features': path.resolve(__dirname, './src/features'),
			'@shared': path.resolve(__dirname, './src/shared'),
		},
	},
	// Frontend reads VITE_* vars from the project root .env (shared with the backend).
	envDir: path.resolve(__dirname, '../'),
	envPrefix: 'VITE_',
	server: {
		host: true,
		port: 5173,
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
