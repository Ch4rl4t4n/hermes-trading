import client from "./client";

/** Maps Marketplace „Community“ sort select na backend sort_listing_rows kľúče. */
const SORT_MAP = {
  newest: "newest",
  top: "top",
  popular: "popularity",
};

export async function getMarketplaceUserAgentListings({ sort = "newest", limit = 60 } = {}) {
  try {
    const apiSort = SORT_MAP[sort] || "pnl_week";
    const { data } = await client.get("/api/marketplace/listings", {
      params: { sort: apiSort, limit },
    });
    return { listings: Array.isArray(data?.listings) ? data.listings : [], error: null };
  } catch (error) {
    return { listings: [], error };
  }
}

export async function cloneMarketplaceListing(publicId) {
  try {
    const { data } = await client.post(`/api/marketplace/listings/${encodeURIComponent(String(publicId))}/clone`, {});
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}
