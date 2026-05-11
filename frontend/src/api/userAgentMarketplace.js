import client from "./client";

export async function publishUserAgent(agentId, description) {
  try {
    const { data } = await client.post("/api/marketplace/user-agents/publish", {
      agent_id: agentId,
      description,
    });
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function unpublishUserAgent(agentId) {
  try {
    const { data } = await client.post("/api/marketplace/user-agents/unpublish", {
      agent_id: agentId,
    });
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}
