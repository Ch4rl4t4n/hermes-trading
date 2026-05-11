import { useMemo, useState } from "react";

import { publishUserAgent } from "../api/userAgentMarketplace";

function apiErr(error, fallback) {
  return error?.response?.data?.message || error?.response?.data?.error || error?.message || fallback;
}

export default function PublishBuilderAgentModal({ agent, open, onClose, onToast, onPublished }) {
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const len = useMemo(() => String(description || "").trim().length, [description]);

  if (!open || !agent) return null;

  const onSubmit = async () => {
    setSubmitting(true);
    setError("");
    const result = await publishUserAgent(agent.id, description.trim());
    if (result.error || result.data?.success === false) {
      const msg = result.data?.message || apiErr(result.error, "Publish failed.");
      setError(msg);
      onToast?.(msg);
      setSubmitting(false);
      return;
    }
    onToast?.("Agent submitted for moderator review.");
    setDescription("");
    onPublished?.();
    setSubmitting(false);
    onClose?.();
  };

  return (
    <div className="developer-modal-backdrop" role="presentation" onClick={() => onClose?.()}>
      <div className="glass submit-agent-modal" role="dialog" aria-modal="true" onClick={(ev) => ev.stopPropagation()}>
        <h4 style={{ marginTop: 0, marginBottom: 12 }}>Publish to marketplace</h4>
        <p className="text-3 fs-13" style={{ marginTop: 0 }}>
          Agent <strong>{agent.name}</strong> ({agent.symbol}) — after submission an administrator will review it. Requires an active agent for at least 14 days, ≥20 paper trades, and positive aggregate P&amp;L.
        </p>
        <label className="col gap-2 fs-12 text-2">
          Community description (50–500 characters)
          <textarea
            className="inp"
            id="publish-description"
            value={description}
            rows={5}
            maxLength={500}
            placeholder="Strategy, time window, risk rules…"
            onChange={(ev) => setDescription(ev.target.value)}
          />
        </label>
        <div className="row between fs-12" style={{ marginTop: 6 }}>
          <span className={len >= 50 && len <= 500 ? "publish-req-ok" : "publish-req-bad"}>
            {len} / 500 {len < 50 ? "(minimum 50)" : ""}
          </span>
        </div>
        {error ? (
          <div className="glass" style={{ padding: 10, marginTop: 12, border: "1px solid oklch(0.65 0.2 25 / 0.5)" }}>
            <span className="fs-13">{error}</span>
          </div>
        ) : null}
        <div className="row gap-2" style={{ marginTop: 18, justifyContent: "flex-end" }}>
          <button type="button" className="pill pill-gray" style={{ border: "none" }} disabled={submitting} onClick={() => onClose?.()}>
            Cancel
          </button>
          <button
            type="button"
            className="pill pill-violet"
            style={{ border: "none" }}
            disabled={submitting || len < 50 || len > 500}
            onClick={onSubmit}
          >
            {submitting ? "Sending…" : "Submit for review"}
          </button>
        </div>
      </div>
    </div>
  );
}
