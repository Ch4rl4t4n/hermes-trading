import client from "./client";

export async function getCommunityAgents({ category = "all", sort = "newest" } = {}) {
  try {
    const { data } = await client.get("/api/community/agents", { params: { category, sort } });
    return { data: Array.isArray(data) ? data : [], error: null };
  } catch (error) {
    return { data: [], error };
  }
}

export async function submitCommunityAgent(payload) {
  try {
    const { data } = await client.post("/api/community/my-agents", payload);
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function getMyCommunityAgents() {
  try {
    const { data } = await client.get("/api/community/my-agents");
    return { data: Array.isArray(data) ? data : [], error: null };
  } catch (error) {
    return { data: [], error };
  }
}

export async function getPendingCommunityAgents() {
  try {
    const { data } = await client.get("/api/admin/community/agents/pending");
    return { data: Array.isArray(data) ? data : [], error: null };
  } catch (error) {
    return { data: [], error };
  }
}

export async function reviewCommunityAgent(agentId, action, reason = "") {
  try {
    const { data } = await client.post(`/api/admin/community/agents/${encodeURIComponent(String(agentId))}/review`, { action, reason });
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}
