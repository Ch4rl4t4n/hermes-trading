import { useMemo, useState } from "react";

import { submitCommunityAgent } from "../api/community";

const SYMBOL_OPTIONS = [
  "BTC/USD",
  "ETH/USD",
  "SOL/USD",
  "BNB/USD",
  "AAPL",
  "TSLA",
  "NVDA",
  "QQQ",
  "GLD",
  "USO",
];

const STRATEGY_OPTIONS = [
  "momentum",
  "mean_reversion",
  "breakout",
  "scalping",
  "swing",
  "grid",
  "trend_following",
];

export default function SubmitAgentModal({ open, onClose, onSubmitted, onToast }) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    name: "",
    symbol: "BTC/USD",
    category: "crypto",
    strategy: "momentum",
    riskLevel: "medium",
    description: "",
    priceMonthly: 0,
  });

  const descriptionLen = useMemo(() => String(form.description || "").length, [form.description]);

  if (!open) return null;

  const setField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = async () => {
    setSubmitting(true);
    setError("");
    const result = await submitCommunityAgent({
      name: form.name,
      symbol: form.symbol,
      category: form.category,
      strategy: form.strategy,
      risk_level: form.riskLevel,
      description: form.description,
      price_monthly: Number(form.priceMonthly || 0),
    });
    if (result.error) {
      setError(result.error?.response?.data?.error || "Submit failed.");
      setSubmitting(false);
      return;
    }
    onToast?.("Agent submitted for review. We'll notify you within 24h.");
    onSubmitted?.();
    setSubmitting(false);
    onClose?.();
  };

  return (
    <div className="developer-modal-backdrop" role="presentation" onClick={() => onClose?.()}>
      <div className="glass submit-agent-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
        <h4 style={{ marginTop: 0, marginBottom: 12 }}>Submit Agent</h4>
        <div className="col gap-2">
          <label className="fs-12 text-3">Agent Name</label>
          <input className="inp" value={form.name} maxLength={100} onChange={(event) => setField("name", event.target.value)} />
        </div>

        <div className="submit-grid-2">
          <label className="col gap-2">
            <span className="fs-12 text-3">Symbol</span>
            <select className="bt-field" value={form.symbol} onChange={(event) => setField("symbol", event.target.value)}>
              {SYMBOL_OPTIONS.map((symbol) => (
                <option key={symbol} value={symbol}>{symbol}</option>
              ))}
            </select>
          </label>
          <label className="col gap-2">
            <span className="fs-12 text-3">Strategy</span>
            <select className="bt-field" value={form.strategy} onChange={(event) => setField("strategy", event.target.value)}>
              {STRATEGY_OPTIONS.map((strategy) => (
                <option key={strategy} value={strategy}>{strategy}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="col gap-2">
          <span className="fs-12 text-3">Category</span>
          <div className="row gap-2" style={{ flexWrap: "wrap" }}>
            {["crypto", "stocks", "commodities"].map((category) => (
              <button
                key={category}
                type="button"
                className={`pill ${form.category === category ? "pill-violet" : "pill-gray"}`}
                style={{ border: "none" }}
                onClick={() => setField("category", category)}
              >
                {category[0].toUpperCase() + category.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div className="col gap-2">
          <span className="fs-12 text-3">Risk Level</span>
          <div className="row gap-2" style={{ flexWrap: "wrap" }}>
            {["low", "medium", "high"].map((risk) => (
              <button
                key={risk}
                type="button"
                className={`pill ${form.riskLevel === risk ? "pill-violet" : "pill-gray"}`}
                style={{ border: "none" }}
                onClick={() => setField("riskLevel", risk)}
              >
                {risk[0].toUpperCase() + risk.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div className="col gap-2">
          <label className="fs-12 text-3" htmlFor="submitAgentDescription">Description</label>
          <textarea
            id="submitAgentDescription"
            className="bt-field"
            rows={5}
            maxLength={1000}
            value={form.description}
            onChange={(event) => setField("description", event.target.value)}
            style={{ marginBottom: 0 }}
          />
          <span className="text-3 fs-12">{descriptionLen}/1000</span>
        </div>

        <div className="col gap-2">
          <label className="fs-12 text-3" htmlFor="submitAgentPrice">Monthly Price ($)</label>
          <input
            id="submitAgentPrice"
            type="number"
            min={0}
            max={99}
            className="inp"
            value={form.priceMonthly}
            onChange={(event) => setField("priceMonthly", event.target.value)}
          />
        </div>

        {error ? <div className="developer-error" style={{ marginTop: 10 }}>{error}</div> : null}

        <div className="row gap-2" style={{ justifyContent: "flex-end", marginTop: 14 }}>
          <button type="button" className="pill pill-gray" style={{ border: "none" }} onClick={() => onClose?.()}>
            Cancel
          </button>
          <button
            type="button"
            className="pill pill-violet"
            style={{ border: "none" }}
            onClick={handleSubmit}
            disabled={submitting}
          >
            {submitting ? "Submitting..." : "Submit for Review"}
          </button>
        </div>
      </div>
    </div>
  );
}
