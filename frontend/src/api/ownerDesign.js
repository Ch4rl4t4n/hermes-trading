import client from "./client";

export async function getOwnerDesignSchema() {
  try {
    const { data } = await client.get("/api/owner/design/schema");
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function getOwnerDesignTemplate() {
  try {
    const { data } = await client.get("/api/owner/design/schema-template");
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function getOwnerDesignHistory(limit = 30) {
  try {
    const { data } = await client.get("/api/owner/design/history", { params: { limit } });
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function applyOwnerDesignSchema(schema, label = "") {
  try {
    const { data } = await client.post("/api/owner/design/apply", { schema, label });
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function revertOwnerDesignVersion(versionId) {
  try {
    const { data } = await client.post("/api/owner/design/revert", { version_id: versionId });
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function aiAnalyzeOwnerDesign(schema) {
  try {
    const { data } = await client.post("/api/owner/design/analyze", { schema });
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function aiGenerateOwnerDesign(prompt, schema) {
  try {
    const { data } = await client.post("/api/owner/design/generate", { prompt, schema });
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function importOwnerDesign(payload) {
  try {
    const { data } = await client.post("/api/owner/design/import", payload);
    return { data, error: null };
  } catch (error) {
    return { data: null, error };
  }
}

export async function importOwnerDesignBundle(file) {
  const fd = new FormData();
  fd.append("file", file);
  try {
    const { data } = await client.post("/api/owner/design/import-bundle", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return { data, error: null };
  } catch (error) {
    const data = error?.response?.data || null;
    return { data, error };
  }
}
