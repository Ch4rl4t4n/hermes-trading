import axios from "axios";
import { STORAGE_KEYS } from "../utils/storageKeys";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
  withCredentials: true,
  timeout: 10000,
});

client.interceptors.request.use((config) => {
  let token;
  let csrf;
  try {
    token = localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);
    csrf = localStorage.getItem(STORAGE_KEYS.AUTH_CSRF_TOKEN);
  } catch {
    // Ignore storage errors in private browsing mode.
  }
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (csrf && ["post", "put", "patch", "delete"].includes(String(config.method || "").toLowerCase())) {
    config.headers["X-CSRF-Token"] = csrf;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      try {
        localStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
        localStorage.removeItem(STORAGE_KEYS.AUTH_CSRF_TOKEN);
      } catch {
        // Ignore storage errors.
      }
    }
    if (error?.response?.status === 403) {
      error.userMessage = error?.response?.data?.error || "Admin access required";
    }
    return Promise.reject(error);
  },
);

export default client;

