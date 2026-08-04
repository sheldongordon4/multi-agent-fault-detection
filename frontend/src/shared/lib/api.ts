import axios from 'axios';


const RAW_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(
	/\/+$/,
	''
);

export const API_BASE_URL = RAW_BASE || 'http://localhost:8000';

export const api = axios.create({
	baseURL: API_BASE_URL,
	headers: {
		'Content-Type': 'application/json',
		Accept: 'application/json',
	},
	// NOT `withCredentials: true`. MAFD has no auth, so the API sets
	// `allow_credentials=False` with `allow_origins=["*"]` (app/api/main.py).
	// Sending credentials makes the browser demand an
	// `Access-Control-Allow-Credentials` header the server never returns — and a
	// wildcard origin is invalid for credentialed requests — so every call fails
	// CORS. Keep credentials off to match the backend.
	withCredentials: false,
});

export default api;
