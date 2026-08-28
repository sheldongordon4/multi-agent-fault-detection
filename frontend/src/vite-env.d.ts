/// <reference types="vite/client" />

// Typed access to the VITE_* vars this app reads (see docker-compose.dev.yaml).
interface ImportMetaEnv {
	readonly VITE_API_URL?: string;
	/** Grid basemap source: 'offline' (self-hosted Jamaica .pmtiles) or 'online'. */
	readonly VITE_MAP_MODE?: 'online' | 'offline';
}

interface ImportMeta {
	readonly env: ImportMetaEnv;
}
