import { useCallback, useEffect, useMemo, useState } from "react";

import { createDeveloperKey, listDeveloperKeys, revokeDeveloperKey } from "../api/developer";

function apiErrorMessage(error, fallback) {
  return error?.response?.data?.error || error?.message || fallback;
}

function toBadgeClass(isActive) {
  return isActive ? "pill pill-violet" : "pill pill-gray";
}

export default function Developer({ user }) {
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [revokingId, setRevokingId] = useState(null);
  const [keys, setKeys] = useState([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState("Default");
  const [freshKey, setFreshKey] = useState(null);
  const [error, setError] = useState("");

  const tier = String(user?.tier || "basic").toLowerCase();
  const eliteAccess = tier === "elite" || tier === "admin";

  const stats = useMemo(() => {
    const totals = keys.reduce(
      (acc, key) => {
        acc.today += Number(key.requests_today || 0);
        acc.total += Number(key.requests_total || 0);
        acc.limit += Number(key.rate_limit || 0);
        return acc;
      },
      { today: 0, total: 0, limit: 0 },
    );
    return totals;
  }, [keys]);

  const loadKeys = useCallback(async () => {
    if (!eliteAccess) {
      setLoading(false);
      return;
    }
    setLoading(true);
    const result = await listDeveloperKeys();
    if (result.error) {
      setError(apiErrorMessage(result.error, "Could not load API keys."));
    } else {
      setKeys(result.data || []);
      setError("");
    }
    setLoading(false);
  }, [eliteAccess]);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadKeys();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadKeys]);

  const onCreateKey = async () => {
    setCreating(true);
    const result = await createDeveloperKey(newKeyName);
    if (result.error) {
      setError(apiErrorMessage(result.error, "Could not create API key."));
    } else {
      setFreshKey(result.data);
      setShowCreateModal(false);
      setNewKeyName("Default");
      setError("");
      await loadKeys();
    }
    setCreating(false);
  };

  const onRevokeKey = async (keyId) => {
    setRevokingId(keyId);
    const result = await revokeDeveloperKey(keyId);
    if (result.error) {
      setError(apiErrorMessage(result.error, "Could not revoke API key."));
    } else {
      await loadKeys();
    }
    setRevokingId(null);
  };

  const onCopyFreshKey = async () => {
    try {
      await navigator.clipboard.writeText(String(freshKey?.key || ""));
    } catch {
      setError("Copy failed. Please copy manually.");
    }
  };

  if (!eliteAccess) {
    return (
      <section className="page-content">
        <article className="glass" style={{ padding: 16, maxWidth: 900 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h3 style={{ margin: 0 }}>Developer API</h3>
            <span className="pill pill-gray">Elite Required</span>
          </div>
          <div className="glass" style={{ padding: 18, border: "1px solid oklch(1 0 0 / 0.08)" }}>
            <div className="row gap-2" style={{ alignItems: "center", marginBottom: 10 }}>
              <span aria-hidden="true">🔒</span>
              <strong>Elite tier required</strong>
            </div>
            <p className="text-3" style={{ marginTop: 0 }}>
              Upgrade your plan to create and manage API keys for automation, reporting, and external integrations.
            </p>
            <button
              type="button"
              className="pill pill-violet"
              style={{ border: "none" }}
              onClick={() => {
                window.location.href = "/pricing";
              }}
            >
              Upgrade to Elite
            </button>
          </div>
        </article>
      </section>
    );
  }

  return (
    <section className="page-content">
      <article className="glass developer-page" style={{ padding: 16, maxWidth: 980 }}>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div>
            <h3 style={{ margin: 0 }}>Developer API</h3>
            <span className="pill pill-violet" style={{ marginTop: 8, display: "inline-flex" }}>Elite</span>
          </div>
          <button
            type="button"
            className="pill pill-violet"
            style={{ border: "none" }}
            onClick={() => setShowCreateModal(true)}
            disabled={keys.filter((key) => key.is_active).length >= 3}
          >
            Create New Key
          </button>
        </div>

        {error ? <div className="developer-error">{error}</div> : null}

        {freshKey?.key ? (
          <div className="developer-fresh-key">
            <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
              <strong>New API key created</strong>
              <button type="button" className="pill pill-gray" style={{ border: "none" }} onClick={onCopyFreshKey}>
                Copy
              </button>
            </div>
            <code className="developer-code-block">{freshKey.key}</code>
            <p className="text-3 fs-12" style={{ marginBottom: 0 }}>Save this key - it will not be shown again.</p>
          </div>
        ) : null}

        <section className="developer-section">
          <h4>API Keys</h4>
          {loading ? <div className="text-3">Loading keys...</div> : null}
          {!loading && keys.length === 0 ? <div className="text-3">No keys yet. Create your first key.</div> : null}
          <div className="developer-key-list">
            {keys.map((key) => (
              <div key={key.id} className="developer-key-item">
                <div className="col" style={{ minWidth: 0 }}>
                  <strong>{key.name || "Default"}</strong>
                  <span className="text-3 fs-12">Prefix: {key.key_prefix}</span>
                  <span className="text-3 fs-12">Usage today: {key.requests_today || 0} / {key.rate_limit || 1000}</span>
                  <span className="text-3 fs-12">Total requests: {key.requests_total || 0}</span>
                </div>
                <div className="row gap-2" style={{ alignItems: "center" }}>
                  <span className={toBadgeClass(Boolean(key.is_active))}>{key.is_active ? "ACTIVE" : "REVOKED"}</span>
                  <button
                    type="button"
                    className="pill pill-gray"
                    style={{ border: "none" }}
                    disabled={!key.is_active || revokingId === key.id}
                    onClick={() => onRevokeKey(key.id)}
                  >
                    {revokingId === key.id ? "Revoking..." : "Revoke"}
                  </button>
                </div>
              </div>
            ))}
          </div>
          <p className="text-3 fs-12" style={{ marginBottom: 0 }}>Maximum 3 active keys per account.</p>
        </section>

        <section className="developer-section">
          <h4>Quick Stats</h4>
          <div className="developer-stats">
            <div className="glass developer-stat-card">
              <span className="text-3 fs-12">Requests Today</span>
              <strong>{stats.today}</strong>
            </div>
            <div className="glass developer-stat-card">
              <span className="text-3 fs-12">Requests Total</span>
              <strong>{stats.total}</strong>
            </div>
            <div className="glass developer-stat-card">
              <span className="text-3 fs-12">Daily Rate Limit</span>
              <strong>{stats.limit || 1000}</strong>
            </div>
          </div>
        </section>

        <section className="developer-section">
          <h4>API Docs</h4>
          <details className="glass developer-docs" open>
            <summary>Authentication and base URL</summary>
            <p>Base URL: <code>https://letagentscook.lol/api/v1/</code></p>
            <p>Auth header: <code>X-API-Key: hms_...</code></p>
          </details>
          <details className="glass developer-docs">
            <summary>Available endpoints</summary>
            <ul className="developer-endpoints">
              <li><code>GET /agents</code></li>
              <li><code>GET /agents/{"{id}"}/trades?limit=50</code></li>
              <li><code>GET /pnl</code></li>
            </ul>
          </details>
          <details className="glass developer-docs">
            <summary>Code examples</summary>
            <div className="developer-code-title">curl</div>
            <pre className="developer-code-block"><code>{'curl -H "X-API-Key: hms_..." https://letagentscook.lol/api/v1/agents'}</code></pre>
            <div className="developer-code-title">Python</div>
            <pre className="developer-code-block"><code>{`import requests

url = "https://letagentscook.lol/api/v1/agents"
headers = {"X-API-Key": "hms_..."}
response = requests.get(url, headers=headers, timeout=10)
print(response.json())`}</code></pre>
          </details>
        </section>
      </article>

      {showCreateModal ? (
        <div className="developer-modal-backdrop" role="presentation" onClick={() => setShowCreateModal(false)}>
          <div className="glass developer-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <h4 style={{ marginTop: 0 }}>Create API Key</h4>
            <label className="fs-12 text-3" htmlFor="developerKeyName">Key name</label>
            <input
              id="developerKeyName"
              className="inp"
              value={newKeyName}
              maxLength={100}
              onChange={(event) => setNewKeyName(event.target.value)}
              style={{ marginTop: 8, marginBottom: 14 }}
            />
            <div className="row gap-2" style={{ justifyContent: "flex-end" }}>
              <button type="button" className="pill pill-gray" style={{ border: "none" }} onClick={() => setShowCreateModal(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="pill pill-violet"
                style={{ border: "none" }}
                onClick={onCreateKey}
                disabled={creating}
              >
                {creating ? "Creating..." : "Create"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
