/**
 * Swarm v2 API client.
 *
 * Bridges Flask session → FastAPI JWT, then calls /api/v2/swarm/* endpoints.
 * Token is cached in-memory (refreshed on 401 or after exp).
 */
import client from "./client";

const TOKEN_TTL_BUFFER_MS = 60 * 1000;

let cachedToken = null;
let cachedTokenExpiresAt = 0;
let inflightRefresh = null;

async function refreshFastapiToken() {
  if (inflightRefresh) return inflightRefresh;
  inflightRefresh = (async () => {
    const { data } = await client.post("/api/v1/auth/fastapi-token");
    if (!data?.fastapi_token) throw new Error("No FastAPI token issued");
    cachedToken = data.fastapi_token;
    const expiresInMs = (Number(data.expires_in || 3600) * 1000) - TOKEN_TTL_BUFFER_MS;
    cachedTokenExpiresAt = Date.now() + Math.max(60_000, expiresInMs);
    return cachedToken;
  })().finally(() => {
    inflightRefresh = null;
  });
  return inflightRefresh;
}

async function getFastapiToken() {
  if (cachedToken && Date.now() < cachedTokenExpiresAt) return cachedToken;
  return refreshFastapiToken();
}

async function v2Request(method, path, { params, body, retryOn401 = true } = {}) {
  const token = await getFastapiToken();
  const url = path.startsWith("/api/v2") ? path : `/api/v2${path}`;
  try {
    const response = await client.request({
      method,
      url,
      params,
      data: body,
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  } catch (error) {
    if (retryOn401 && error?.response?.status === 401) {
      cachedToken = null;
      cachedTokenExpiresAt = 0;
      return v2Request(method, path, { params, body, retryOn401: false });
    }
    throw error;
  }
}

export const swarmApi = {
  status: () => v2Request("GET", "/swarm/status"),
  swarms: () => v2Request("GET", "/swarm/swarms"),
  agents: ({ swarm, aliveOnly } = {}) =>
    v2Request("GET", "/swarm/agents", {
      params: { swarm, alive_only: aliveOnly ? true : undefined },
    }),
  agent: (agentId) => v2Request("GET", `/swarm/agents/${encodeURIComponent(agentId)}`),
  queue: (limit = 25) => v2Request("GET", "/swarm/queue", { params: { limit } }),
  routingLog: (limit = 20) => v2Request("GET", "/swarm/routing-log", { params: { limit } }),
  capabilities: () => v2Request("GET", "/swarm/capabilities"),
  simulate: ({ taskType, requiredCapabilities, preferredSwarm, priority }) =>
    v2Request("POST", "/swarm/route", {
      body: {
        task_type: taskType,
        required_capabilities: requiredCapabilities,
        preferred_swarm: preferredSwarm,
        priority,
      },
    }),
  dispatch: ({ taskType, payload, requiredCapabilities, preferredSwarm, priority }) =>
    v2Request("POST", "/swarm/dispatch", {
      body: {
        task_type: taskType,
        payload,
        required_capabilities: requiredCapabilities,
        preferred_swarm: preferredSwarm,
        priority,
      },
    }),
  seed: () => v2Request("POST", "/swarm/seed"),
};

export function clearSwarmTokenCache() {
  cachedToken = null;
  cachedTokenExpiresAt = 0;
}

export default swarmApi;
