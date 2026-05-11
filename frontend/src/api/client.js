import axios from "axios";
import { STORAGE_KEYS } from "../utils/storageKeys";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
  withCredentials: true,
  timeout: 10000,
});

let csrfRefreshInflight = null;

async function refreshCsrfToken() {
  // Single-flight: ak už refresh beží, všetci čakajú na ten istý promise
  if (csrfRefreshInflight) return csrfRefreshInflight;
  csrfRefreshInflight = (async () => {
    try {
      const res = await axios.get("/api/auth/csrf", {
        withCredentials: true,
        timeout: 8000,
      });
      const tok = res?.data?.csrf_token;
      if (tok) {
        try {
          localStorage.setItem(STORAGE_KEYS.AUTH_CSRF_TOKEN, tok);
        } catch {
          // localStorage may be disabled in private mode
        }
        return tok;
      }
      return null;
    } catch {
      return null;
    } finally {
      csrfRefreshInflight = null;
    }
  })();
  return csrfRefreshInflight;
}

export async function ensureCsrfToken() {
  let csrf = null;
  try {
    csrf = localStorage.getItem(STORAGE_KEYS.AUTH_CSRF_TOKEN);
  } catch {
    csrf = null;
  }
  if (csrf) return csrf;
  return refreshCsrfToken();
}

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
  async (error) => {
    const status = error?.response?.status;
    const data = error?.response?.data;
    const original = error?.config;

    // Auto-retry pri Invalid/Missing CSRF: zoberieme nový token a opakujeme original request raz.
    if (
      status === 403 &&
      data?.csrf_required &&
      original &&
      !original.__csrfRetried
    ) {
      original.__csrfRetried = true;
      const fresh = await refreshCsrfToken();
      if (fresh) {
        original.headers = original.headers || {};
        original.headers["X-CSRF-Token"] = fresh;
        return client.request(original);
      }
    }

    if (status === 401) {
      try {
        localStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
        localStorage.removeItem(STORAGE_KEYS.AUTH_CSRF_TOKEN);
      } catch {
        // Ignore storage errors.
      }
    }
    if (status === 403) {
      error.userMessage = data?.error || "Admin access required";
    }
    return Promise.reject(error);
  },
);

export default client;
