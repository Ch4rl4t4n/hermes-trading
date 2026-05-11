import client from "./client";

export async function listBuilderAgents() {
  try {
    const { data } = await client.get("/api/agent-builder/my-agents");
    return { agents: Array.isArray(data?.agents) ? data.agents : [], error: null, raw: data };
  } catch (error) {
    return { agents: [], error, raw: null };
  }
}

export async function fetchWatcherSettings(agentId) {
  const { data } = await client.get(`/api/agents/user/${encodeURIComponent(String(agentId))}/watcher-settings`);
  return data;
}

export async function saveWatcherSettings(agentId, watcherConfig) {
  const { data } = await client.post(`/api/agents/user/${encodeURIComponent(String(agentId))}/watcher-settings`, {
    watcher_config: watcherConfig,
  });
  return data;
}

export async function resetWatcherSettings(agentId) {
  const { data } = await client.post(
    `/api/agents/user/${encodeURIComponent(String(agentId))}/reset-watcher-settings`,
    {},
  );
  return data;
}
