import { useEffect, useRef, useState } from "react";
import { useBreakpoint } from "../hooks/useBreakpoint";
import { createAgentFromConversation, deployAgent } from "../api/builder";
import VoiceButton from "../components/VoiceButton";

const wizardSteps = ["Strategy", "Risk", "Schedule", "Review"];

export default function Builder({ onToast, onNav }) {
  const { isDesktop } = useBreakpoint();
  const [mode, setMode] = useState("chat");
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Hi! I'm your agent builder. Tell me what kind of trading agent you want to create. For example: 'Create a Bitcoin momentum agent that buys on dips'",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [agentPreview, setAgentPreview] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    name: "Momentum Nova",
    symbol: "BTC/USD",
    category: "Crypto",
    risk: "medium",
    drawdown: 9,
    positionSize: 2.2,
    session: "24/7",
    days: ["Mon", "Tue", "Wed", "Thu", "Fri"],
  });
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const setField = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));
  const progress = `${(step / 4) * 100}%`;

  const sendMessage = async (explicitText) => {
    const normalizedText = String(explicitText ?? input).trim();
    if (!normalizedText || loading) return;
    const userMsg = { role: "user", content: normalizedText };
    setMessages((prev) => [...prev, userMsg]);
    if (explicitText === undefined) setInput("");
    setLoading(true);
    try {
      const result = await createAgentFromConversation([...messages, userMsg]);
      const res = result.data;
      if (!res) throw new Error("builder-response-empty");
      setMessages((prev) => [...prev, { role: "assistant", content: res.message }]);
      if (res.agentConfig) {
        setAgentPreview(res.agentConfig);
        setConfirmed(false);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Sorry, I had trouble processing that. Try describing your agent differently." },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!agentPreview || loading) return;
    setLoading(true);
    try {
      const result = await deployAgent(agentPreview);
      if (!result.data) throw new Error("deploy-failed");
      setConfirmed(true);
      onToast?.("Agent deployed successfully!");
      setTimeout(() => onNav?.("dashboard"), 1200);
    } catch {
      onToast?.("Deploy failed — try again");
    } finally {
      setLoading(false);
    }
  };

  const getCategoryPill = (category) => {
    const lower = String(category || "").toLowerCase();
    if (lower === "crypto") return "pill-violet";
    if (lower === "stocks") return "pill-green";
    if (lower === "commodities") return "pill-amber";
    return "pill-gray";
  };

  const previewCard = (
    <div className="glass" style={{ padding: 20 }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", color: "var(--text-3)", marginBottom: 12 }}>
        LIVE PREVIEW
      </div>
      {agentPreview ? (
        <>
          <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4 }}>{agentPreview.name}</div>
          <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
            <span className="pill pill-gray">{agentPreview.symbol}</span>
            <span className={`pill ${getCategoryPill(agentPreview.category)}`}>{agentPreview.category}</span>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 8 }}>Strategy: {agentPreview.strategy}</div>
          <div style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 8 }}>Risk: {agentPreview.risk}</div>
          {Array.isArray(agentPreview.indicators) ? (
            <div style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 16 }}>
              Indicators: {agentPreview.indicators.join(", ")}
            </div>
          ) : null}
          {!confirmed ? (
            <button
              onClick={handleConfirm}
              disabled={loading}
              type="button"
              style={{
                width: "100%",
                padding: "12px",
                background: "oklch(0.72 0.18 155)",
                border: "none",
                borderRadius: 10,
                color: "black",
                fontWeight: 700,
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              Deploy Agent ⚡
            </button>
          ) : null}
        </>
      ) : (
        <div style={{ color: "var(--text-3)", fontSize: 13, textAlign: "center", padding: "20px 0" }}>
          Describe your agent in the chat and I&apos;ll build the preview here
        </div>
      )}
    </div>
  );

  const tipsCard = (
    <div className="glass" style={{ padding: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", color: "var(--text-3)", marginBottom: 10 }}>
        TIPS
      </div>
      {[
        "Mention symbol (BTC, ETH, AAPL)",
        "Specify risk level (safe/medium/aggressive)",
        "Add indicators (RSI, MACD, EMA)",
        "Set trading hours or days",
      ].map((tip) => (
        <div
          key={tip}
          style={{
            fontSize: 12,
            color: "var(--text-2)",
            marginBottom: 6,
            paddingLeft: 8,
            borderLeft: "2px solid oklch(0.72 0.18 295 / 0.4)",
          }}
        >
          {tip}
        </div>
      ))}
    </div>
  );

  const wizardContent = (
    <>
      <article className="glass col gap-3" style={{ padding: 14 }}>
        <div className="row between fs-12 text-3">
          <span>Step {step} of 4</span>
          <span>{wizardSteps[step - 1]}</span>
        </div>
        <div className="progress">
          <div className="progress-fill" style={{ width: progress }} />
        </div>
      </article>

      {step === 1 ? (
        <article className="glass col gap-3 ab-step-panel active" style={{ padding: 14 }}>
          <h3>Strategy</h3>
          <label className="col gap-2 fs-12 text-2">
            Agent Name
            <input value={form.name} onChange={(e) => setField("name", e.target.value)} />
          </label>
          <label className="col gap-2 fs-12 text-2">
            Symbol
            <input value={form.symbol} onChange={(e) => setField("symbol", e.target.value)} />
          </label>
          <label className="col gap-2 fs-12 text-2">
            Category
            <select value={form.category} onChange={(e) => setField("category", e.target.value)}>
              <option>Crypto</option>
              <option>Stocks</option>
              <option>Commodities</option>
              <option>Forex</option>
            </select>
          </label>
        </article>
      ) : null}

      {step === 2 ? (
        <article className="glass col gap-3 ab-step-panel active" style={{ padding: 14 }}>
          <h3>Risk</h3>
          <label className="col gap-2 fs-12 text-2">
            Risk Level
            <select value={form.risk} onChange={(e) => setField("risk", e.target.value)}>
              <option>low</option>
              <option>medium</option>
              <option>high</option>
            </select>
          </label>
          <label className="col gap-2 fs-12 text-2">
            Max Drawdown: {form.drawdown}%
            <input type="range" min="2" max="25" value={form.drawdown} onChange={(e) => setField("drawdown", Number(e.target.value))} />
          </label>
          <label className="col gap-2 fs-12 text-2">
            Position Size %
            <input type="number" value={form.positionSize} onChange={(e) => setField("positionSize", Number(e.target.value))} />
          </label>
        </article>
      ) : null}

      {step === 3 ? (
        <article className="glass col gap-3 ab-step-panel active" style={{ padding: 14 }}>
          <h3>Schedule</h3>
          <label className="col gap-2 fs-12 text-2">
            Trading Hours
            <select value={form.session} onChange={(e) => setField("session", e.target.value)}>
              <option>24/7</option>
              <option>US Session</option>
              <option>EU Session</option>
              <option>Asia Session</option>
            </select>
          </label>
          <div className="col gap-2">
            <span className="text-2 fs-12">Active Days</span>
            <div className="row gap-2" style={{ flexWrap: "wrap" }}>
              {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => (
                <button
                  key={day}
                  className={`pill ${form.days.includes(day) ? "pill-violet" : "pill-gray"}`}
                  style={{ border: "none" }}
                  type="button"
                  onClick={() => setField("days", form.days.includes(day) ? form.days.filter((d) => d !== day) : [...form.days, day])}
                >
                  {day}
                </button>
              ))}
            </div>
          </div>
        </article>
      ) : null}

      {step === 4 ? (
        <article className="glass col gap-2 ab-step-panel active" style={{ padding: 14 }}>
          <h3>Review</h3>
          <p className="fs-13 text-2">
            {form.name} · {form.symbol} · {form.category}
          </p>
          <p className="fs-13 text-2">
            Risk {form.risk} · Max DD {form.drawdown}% · Size {form.positionSize}%
          </p>
          <p className="fs-13 text-2">
            Session {form.session} · Days {form.days.join(", ")}
          </p>
          <button
            type="button"
            onClick={() => onToast?.("Agent deployed to paper trading")}
            style={{
              border: "none",
              borderRadius: 12,
              padding: "11px 14px",
              fontWeight: 700,
              background: "linear-gradient(120deg,#8b5cf6,#06b6d4)",
              color: "#fff",
            }}
          >
            Deploy Agent
          </button>
        </article>
      ) : null}

      <div className="ab-nav-btns">
        <button onClick={() => setStep((s) => Math.max(1, s - 1))} disabled={step === 1} className="btn btn-ghost" type="button">
          Back
        </button>
        <button onClick={() => setStep((s) => Math.min(4, s + 1))} disabled={step === 4} className="btn" type="button">
          {step === 4 ? "Deploy Agent" : "Next"}
        </button>
      </div>
    </>
  );

  const chatContent = (
    <div className="glass" style={{ flex: 1, display: "flex", flexDirection: "column", padding: 0, overflow: "hidden", minHeight: 420 }}>
      <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
        {messages.map((msg, i) => (
          <div key={`${msg.role}-${i}`} style={{ display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start", marginBottom: 12 }}>
            <div
              style={{
                maxWidth: "75%",
                padding: "10px 14px",
                borderRadius: msg.role === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                background: msg.role === "user" ? "oklch(0.72 0.18 295 / 0.2)" : "oklch(0.16 0.03 260)",
                border: "1px solid oklch(0.22 0.03 260)",
                fontSize: 14,
                lineHeight: 1.5,
                color: "var(--text-1)",
                whiteSpace: "pre-wrap",
              }}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {loading ? (
          <div style={{ display: "flex", gap: 6, padding: "10px 0" }}>
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "oklch(0.72 0.18 295)",
                  animation: `pulse 1.4s ease-in-out ${i * 0.2}s infinite`,
                }}
              />
            ))}
          </div>
        ) : null}
        <div ref={messagesEndRef} />
      </div>

      {messages.length === 1 ? (
        <div style={{ padding: "0 20px 12px", display: "flex", gap: 8, flexWrap: "wrap" }}>
          {[
            "BTC momentum agent, medium risk",
            "Safe gold hedge for long-term",
            "Aggressive ETH scalper",
            "Diversified crypto portfolio agent",
          ].map((prompt) => (
            <button
              key={prompt}
              className="pill pill-gray"
              onClick={() => setInput(prompt)}
              style={{ cursor: "pointer", fontSize: 12, border: "none" }}
              type="button"
            >
              {prompt}
            </button>
          ))}
        </div>
      ) : null}

      <div style={{ padding: "12px 16px", borderTop: "1px solid var(--border-1)", display: "flex", gap: 10 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          placeholder="Describe your trading agent..."
          style={{
            flex: 1,
            background: "oklch(0.16 0.03 260)",
            border: "1px solid oklch(0.22 0.03 260)",
            borderRadius: 10,
            padding: "10px 14px",
            color: "var(--text-1)",
            fontSize: 14,
            outline: "none",
          }}
        />
        <button
          onClick={sendMessage}
          disabled={loading}
          type="button"
          style={{
            background: "oklch(0.72 0.18 295)",
            border: "none",
            borderRadius: 10,
            padding: "10px 18px",
            cursor: "pointer",
            color: "white",
            fontWeight: 600,
            fontSize: 14,
            opacity: loading ? 0.6 : 1,
          }}
        >
          Send
        </button>
        <VoiceButton
          onTranscript={async (transcript) => {
            setInput(transcript);
            await sendMessage(transcript);
          }}
          disabled={loading}
        />
      </div>
    </div>
  );

  return (
    <section className="page-content" style={{ position: "relative" }}>
      <div style={{ position: "absolute", top: 16, right: 20, display: "flex", gap: 8, zIndex: 2 }}>
        <button className={`pill ${mode === "chat" ? "pill-violet" : "pill-gray"}`} onClick={() => setMode("chat")} style={{ cursor: "pointer", border: "none" }} type="button">
          AI Chat
        </button>
        <button className={`pill ${mode === "wizard" ? "pill-violet" : "pill-gray"}`} onClick={() => setMode("wizard")} style={{ cursor: "pointer", border: "none" }} type="button">
          Step Wizard
        </button>
      </div>

      <div style={{ marginTop: 44 }}>
        {mode === "wizard" ? (
          isDesktop ? (
            <div className="builder-desktop">
              <div className="builder-form-wrap">
                <div className="builder-stepper desktop" style={{ alignContent: "start" }}>
                  {wizardSteps.map((name, idx) => {
                    const n = idx + 1;
                    return (
                      <div key={name} className={`row gap-2 stepper-item ${n === step ? "active" : ""}`} style={{ border: "1px solid var(--border-subtle)" }}>
                        <span className={`step-dot ${n <= step ? "done" : ""}`}>{n}</span>
                        <span>{name}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="builder-form">{wizardContent}</div>
              </div>
              <article className="glass col gap-2 builder-preview">
                <h3>Live Preview</h3>
                <strong>{form.name}</strong>
                <div className="row gap-2">
                  <span className="pill pill-gray">{form.symbol}</span>
                  <span className="pill pill-violet">{form.category}</span>
                </div>
                <p className="fs-13 text-2">
                  Risk: {form.risk} · Max DD: {form.drawdown}% · Size: {form.positionSize}%
                </p>
                <p className="fs-13 text-3">
                  Session: {form.session} · Days: {form.days.join(", ")}
                </p>
              </article>
            </div>
          ) : (
            <>
              <div className="builder-stepper">
                {wizardSteps.map((name, idx) => {
                  const n = idx + 1;
                  return (
                    <div key={name} className={`row gap-2 stepper-item ${n === step ? "active" : ""}`} style={{ border: "1px solid var(--border-subtle)" }}>
                      <span className={`step-dot ${n <= step ? "done" : ""}`}>{n}</span>
                      <span>{name}</span>
                    </div>
                  );
                })}
              </div>
              {wizardContent}
            </>
          )
        ) : isDesktop ? (
          <div className="row" style={{ gap: 24, height: "calc(100vh - 180px)", alignItems: "stretch" }}>
            {chatContent}
            <div style={{ width: 300, display: "flex", flexDirection: "column", gap: 16 }}>
              {previewCard}
              {tipsCard}
            </div>
          </div>
        ) : (
          <div className="col gap-3">
            {chatContent}
            {agentPreview ? previewCard : null}
            {tipsCard}
          </div>
        )}
      </div>
    </section>
  );
}

