import client from "./client";

/**
 * GET /api/heatmap?metric=volume|change|market_cap|liquidation|open_interest
 * Returns: { items: [...], metric, coming_soon?, cached?, stale? }
 */
export function getHeatmap({ metric = "volume", limit = 20 } = {}) {
  return client.get("/api/heatmap", { params: { metric, limit } });
}
