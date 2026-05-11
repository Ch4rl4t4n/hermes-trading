import client from "./client";

/** GET /api/news/intelligence?limit=12 */
export function listIntelligence({ limit = 12 } = {}) {
  return client.get("/api/news/intelligence", { params: { limit } });
}

/** POST /api/news/intelligence (admin/agent only) */
export function createIntelligence(payload) {
  return client.post("/api/news/intelligence", payload);
}

/** DELETE /api/news/intelligence/:id (admin only) */
export function deleteIntelligence(itemId) {
  return client.delete(`/api/news/intelligence/${itemId}`);
}
