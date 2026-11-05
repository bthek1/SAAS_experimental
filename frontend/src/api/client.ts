import axios, { isAxiosError } from "axios";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL;

// The token itself was refused. Anything else, such as a 502 or a network error while
// `catalog` is down, says nothing about the session, so the user stays logged in.
function refreshWasRejected(error: unknown): boolean {
  const status = isAxiosError(error) ? error.response?.status : undefined;
  return status === 400 || status === 401;
}

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// Attach access token to every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401, attempt a silent token refresh then retry once
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as typeof error.config & {
      _retry?: boolean;
    };
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const refresh = localStorage.getItem("refresh_token");
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE_URL}/api/token/refresh/`, {
            refresh,
          });
          localStorage.setItem("access_token", data.access);
          originalRequest.headers.Authorization = `Bearer ${data.access}`;
          return apiClient(originalRequest);
        } catch (refreshError) {
          if (refreshWasRejected(refreshError)) {
            localStorage.removeItem("access_token");
            localStorage.removeItem("refresh_token");
          }
        }
      }
    }
    return Promise.reject(error);
  },
);
