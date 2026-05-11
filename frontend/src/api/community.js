import client from "./client";

// ─────────────────────────────────────────────────────────────────────────────
// Community Marketplace (user-submitted agents) — pre-existing
// ─────────────────────────────────────────────────────────────────────────────

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
    const { data } = await client.post(
      `/api/admin/community/agents/${encodeURIComponent(String(agentId))}/review`,
      { action, reason },
    );
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Community Feed (CMC-style posts) — dashboard side panel
// ─────────────────────────────────────────────────────────────────────────────

/** GET /api/community/posts?tab=top|latest&symbol=&limit= */
export function listCommunityPosts({ tab = "latest", symbol, limit = 20 } = {}) {
  const params = { tab, limit };
  if (symbol) params.symbol = symbol;
  return client.get("/api/community/posts", { params });
}

/** POST /api/community/posts {content, sentiment?, symbol?} */
export function createCommunityPost({ content, sentiment, symbol }) {
  const body = { content };
  if (sentiment) body.sentiment = sentiment;
  if (symbol) body.symbol = symbol;
  return client.post("/api/community/posts", body);
}

/** POST /api/community/posts/:id/like — toggle */
export function toggleCommunityLike(postId) {
  return client.post(`/api/community/posts/${postId}/like`);
}

/** DELETE /api/community/posts/:id */
export function deleteCommunityPost(postId) {
  return client.delete(`/api/community/posts/${postId}`);
}

/** GET /api/community/sentiment?symbol= */
export function getCommunitySentiment({ symbol } = {}) {
  const params = {};
  if (symbol) params.symbol = symbol;
  return client.get("/api/community/sentiment", { params });
}
