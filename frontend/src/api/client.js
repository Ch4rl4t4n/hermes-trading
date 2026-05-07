import axios from "axios";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
  withCredentials: true,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("hermes_token");
  const csrf = localStorage.getItem("hermes_csrf_token");
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
      localStorage.removeItem("hermes_token");
      localStorage.removeItem("hermes_csrf_token");
    }
    return Promise.reject(error);
  },
);

export default client;

