// Ports for the full-stack suite: dev + 10, so they never collide with `just dev` (8005 / 5174).
export const API_PORT = 8015;
export const WEB_PORT = 5184;
export const API_URL = `http://localhost:${API_PORT}`;
export const WEB_URL = `http://localhost:${WEB_PORT}`;
