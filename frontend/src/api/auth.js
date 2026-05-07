import client from "./client";
import { demoUser } from "../data/demoData";

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
      localStorage.setItem("hermes_token", res.data.token);
    }
    if (res?.data?.csrf_token) {
      localStorage.setItem("hermes_csrf_token", res.data.csrf_token);
    }
    return { success: true, user: normalizeUser(res?.data?.user || res?.data) };
  } catch (err) {
    return {
      success: false,
      error: err?.response?.data?.error || "Login failed",
    };
  }
}

export async function login(payload) {
  return loginWithEmail(payload?.email || payload?.username || "", payload?.password || "", payload?.totp_code || "");
}

export async function loginWithGoogle() {
  window.location.href = "/login/google";
}

export async function googleLogin() {
  return loginWithGoogle();
}

export async function logout() {
  localStorage.removeItem("hermes_token");
  localStorage.removeItem("hermes_csrf_token");
  try {
    await client.post("/api/auth/logout");
  } catch {
    // ignore
  }
}

export async function getCurrentUser() {
  try {
    const res = await client.get("/api/auth/me");
    return normalizeUser(res.data);
  } catch {
    try {
      const statusRes = await client.get("/api/auth/status");
      if (statusRes?.data?.authenticated) {
        return normalizeUser({
          ...statusRes.data.user,
          username: statusRes.data.username,
          email: statusRes.data.email,
          tier: statusRes.data.tier,
          is_admin: statusRes.data.is_admin,
          role: statusRes.data.role,
        });
      }
      return null;
    } catch {
      return null;
    }
  }
}

export async function register(payload) {
  try {
    const { data } = await client.post("/api/auth/register", payload);
    return data;
  } catch {
    return { user: demoUser };
  }
}
