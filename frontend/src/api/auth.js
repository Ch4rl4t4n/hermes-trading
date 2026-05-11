import client from "./client";
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
    isOwner: Boolean(payload.is_owner),
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
  // Full-page navigation — must hit Flask (not SPA index.html fallback).
  window.location.href = "/api/auth/google/start";
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

function userFromStatusPayload(data) {
  if (!data?.authenticated) return null;
  return normalizeUser({
    ...data.user,
    username: data.username,
    email: data.email,
    tier: data.tier,
    is_admin: data.is_admin,
    is_owner: data.is_owner,
    role: data.role,
  });
}

export async function getCurrentUser() {
  let token = null;
  try {
    token = localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN);
  } catch {
    token = null;
  }

  /** Bez Bearer tokenu je ``/api/auth/me`` vždy 401 — šum v konzole; stačí ``/status``. */
  if (!token) {
    try {
      const statusRes = await client.get("/api/auth/status");
      const u = userFromStatusPayload(statusRes?.data);
      return { data: u, error: null };
    } catch {
      return { data: null, error: "auth_unavailable" };
    }
  }

  try {
    const res = await client.get("/api/auth/me");
    return { data: normalizeUser(res.data), error: null };
  } catch {
    try {
      const statusRes = await client.get("/api/auth/status");
      const u = userFromStatusPayload(statusRes?.data);
      return { data: u, error: null };
    } catch {
      return { data: null, error: "auth_unavailable" };
    }
  }
}

/**
 * Registrácia DB účtu. Pri úspechu s automatickým prihlásením uloží token ako login.
 * Pri povolenom email verify vráti needsVerification + message (success bez session).
 */
export async function register(payload) {
  try {
    const res = await client.post("/api/auth/register", {
      email: payload?.email,
      username: payload?.username,
      password: payload?.password,
      confirm_password: payload?.confirm_password ?? payload?.confirmPassword,
      ref_code: payload?.ref_code,
      tos_accepted: payload?.tos_accepted ?? true,
    });
    const d = res.data || {};
    if (d.requires_email_verification) {
      return {
        data: null,
        needsVerification: true,
        message: d.message || "Check your email to verify your account, then sign in.",
        error: null,
      };
    }
    if (d.success && d.token) {
      localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, d.token);
      if (d.csrf_token) {
        localStorage.setItem(STORAGE_KEYS.AUTH_CSRF_TOKEN, d.csrf_token);
      }
      return { data: normalizeUser(d.user), error: null };
    }
    return {
      data: null,
      error: d.message || d.error || "Registration failed",
    };
  } catch (err) {
    const msg =
      err?.response?.data?.error ||
      err?.response?.data?.message ||
      (err?.response?.status === 503 ? "Registration is not available on this server." : "Registration failed");
    return { data: null, error: msg };
  }
}
