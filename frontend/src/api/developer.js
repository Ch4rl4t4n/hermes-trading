import client from "./client";

export async function listDeveloperKeys() {
  try {
    const { data } = await client.get("/api/developer/keys");
    return { data: Array.isArray(data) ? data : [], error: null };
  } catch (error) {
    return { data: [], error };
  }
}

export async function createDeveloperKey(name) {
  try {
    const { data } = await client.post("/api/developer/keys", { name });
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function revokeDeveloperKey(keyId) {
  try {
    const { data } = await client.delete(`/api/developer/keys/${encodeURIComponent(String(keyId))}`);
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}
