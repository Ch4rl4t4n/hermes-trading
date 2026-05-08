import client from "./client";
import { demoUser } from "../data/demoData";
import { STORAGE_KEYS } from "../utils/storageKeys";

function normalizeUser(payload) {
  if (!payload) return null;
  return {
    id: payload.id ?? null,
    email: payload.email ?? null,
    handle: payload.username ? `@${payload.username}` : payload.handle || null,
    name: payload.username || payload.name || payload.email || "Trader",
    tier: payload.tier || "basic",
    isAdmin: Boolean(payload.is_admin || payload.role === "admin"),
    notifications: payload.notifications || 0,
  };
}

export async function loginWithEmail(email, password, totpCode = "") {
  try {
    const res = await client.post("/api/auth/login", {
      email,
      password,
      totp_code: totpCode,
    });
    if (res?.data?.token) {
      localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, res.data.token);
    }
    if (res?.data?.csrf_token) {
      localStorage.setItem(STORAGE_KEYS.AUTH_CSRF_TOKEN, res.data.csrf_token);
    }
    return { data: normalizeUser(res?.data?.user || res?.data), error: null };
  } catch (err) {
    return {
      data: null,
      error: err?.response?.data?.error || "Login failed",
    };
  }
}

export async function login(payload) {
  return loginWithEmail(payload?.email || payload?.username || "", payload?.password || "", payload?.totp_code || "");
}

export async function loginWithGoogle() {
  window.location.href = "/login/google";
  return { data: true, error: null };
}

export async function googleLogin() {
  return loginWithGoogle();
}

export async function logout() {
  localStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
  localStorage.removeItem(STORAGE_KEYS.AUTH_CSRF_TOKEN);
  try {
    await client.post("/api/auth/logout");
    return { data: true, error: null };
  } catch {
    return { data: false, error: null };
  }
}

export async function getCurrentUser() {
  try {
    const res = await client.get("/api/auth/me");
    return { data: normalizeUser(res.data), error: null };
  } catch {
    try {
      const statusRes = await client.get("/api/auth/status");
      if (statusRes?.data?.authenticated) {
        return { data: normalizeUser({
          ...statusRes.data.user,
          username: statusRes.data.username,
          email: statusRes.data.email,
          tier: statusRes.data.tier,
          is_admin: statusRes.data.is_admin,
          role: statusRes.data.role,
        }), error: null };
      }
      return { data: null, error: null };
    } catch {
      return { data: null, error: "auth_unavailable" };
    }
  }
}

export async function register(payload) {
  try {
    const { data } = await client.post("/api/auth/register", payload);
    return { data, error: null };
  } catch {
    return { data: { user: demoUser }, error: "register_failed" };
  }
}
