import { useMemo, useState } from "react";
import { useBreakpoint } from "../hooks/useBreakpoint";

function buildEquityCurve(seed) {
  const points = [];
  let value = 10000;
  for (let i = 0; i < 50; i += 1) {
    const drift = Math.sin((i + seed) / 4) * 120 + (Math.random() - 0.42) * 160;
    value += drift;
    points.push(Math.max(7600, Number(value.toFixed(2))));
  }
  return points;
}

function EquityChart({ points }) {
  if (!points.length) return null;
  const width = 560;
  const height = 240;
  const pad = 10;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = (width - pad * 2) / Math.max(points.length - 1, 1);
  const d = points
    .map((value, idx) => {
      const x = pad + idx * step;
      const y = height - pad - ((value - min) / range) * (height - pad * 2);
      return `${idx === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="240" aria-hidden="true">
      <path d={d} fill="none" stroke="oklch(0.72 0.18 155)" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

export default function Backtest() {
  const { isDesktop } = useBreakpoint();
  const [form, setForm] = useState({
    agent: "BTC Momentum Agent",
    startDate: "2025-01-01",
    endDate: "2025-12-31",
    capital: 10000,
    stopLoss: 8,
    takeProfit: 22,
    positionSize: 18,
  });
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

  const monthly = useMemo(
    () => [
      ["Jan", 2.4], ["Feb", 1.1], ["Mar", -0.8], ["Apr", 3.5],
      ["May", 1.9], ["Jun", 2.8], ["Jul", -1.2], ["Aug", 4.1],
      ["Sep", 2.2], ["Oct", 3.7], ["Nov", 2.9], ["Dec", 1.7],
    ],
    [],
  );

  const update = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const runBacktest = () => {
    setRunning(true);
    setResult(null);
    setTimeout(() => {
      const seed = String(form.agent).length + Number(form.stopLoss) + Number(form.positionSize);
      setResult({
        metrics: {
          totalReturn: 24.3,
          maxDrawdown: -8.2,
          sharpe: 1.84,
          winRate: 67,
        },
        stats: {
          total: 142,
          wins: 95,
          losses: 47,
          avgProfit: 182,
          avgLoss: -89,
        },
        equity: buildEquityCurve(seed),
      });
      setRunning(false);
    }, 2000);
  };

  return (
    <section className="page-content">
      <div className={isDesktop ? "row" : "col"} style={{ gap: 16, alignItems: "stretch" }}>
        <article className="glass col gap-3" style={{ padding: 16, flex: isDesktop ? "0 0 360px" : "1 1 auto" }}>
          <h3>Backtest Configuration</h3>
          <label className="col gap-2 fs-12 text-2">
            Agent
            <select className="bt-field" value={form.agent} onChange={(e) => update("agent", e.target.value)}>
              <option>BTC Momentum Agent</option>
              <option>ETH Swing Agent</option>
              <option>SOL Breakout Agent</option>
              <option>GLD Hedge Agent</option>
            </select>
          </label>
          <div className="row gap-2">
            <label className="col gap-2 fs-12 text-2" style={{ flex: 1 }}>
              Start date
              <input className="bt-field" type="date" value={form.startDate} onChange={(e) => update("startDate", e.target.value)} />
            </label>
            <label className="col gap-2 fs-12 text-2" style={{ flex: 1 }}>
              End date
              <input className="bt-field" type="date" value={form.endDate} onChange={(e) => update("endDate", e.target.value)} />
            </label>
          </div>
          <label className="col gap-2 fs-12 text-2">
            Initial capital ($)
            <input className="bt-field" type="number" min="1000" value={form.capital} onChange={(e) => update("capital", Number(e.target.value))} />
          </label>
          <label className="col gap-2 fs-12 text-2">
            Stop loss %: {form.stopLoss}%
            <input className="ab-range" type="range" min="1" max="20" value={form.stopLoss} onChange={(e) => update("stopLoss", Number(e.target.value))} />
          </label>
          <label className="col gap-2 fs-12 text-2">
            Take profit %: {form.takeProfit}%
            <input className="ab-range" type="range" min="1" max="50" value={form.takeProfit} onChange={(e) => update("takeProfit", Number(e.target.value))} />
          </label>
          <label className="col gap-2 fs-12 text-2">
            Position size %: {form.positionSize}%
            <input className="ab-range" type="range" min="1" max="100" value={form.positionSize} onChange={(e) => update("positionSize", Number(e.target.value))} />
          </label>
          <button
            className="btn"
            type="button"
            style={{ width: "100%", background: "oklch(0.72 0.18 295 / .9)", borderColor: "oklch(0.72 0.18 295 / .9)", color: "#111827" }}
            onClick={runBacktest}
            disabled={running}
          >
            {running ? "Running..." : "Run Backtest"}
          </button>
        </article>

        <article className="glass col gap-3" style={{ padding: 16, flex: 1 }}>
          {!result && !running ? (
            <div className="empty-hint">Run a backtest to generate equity curve and performance metrics.</div>
          ) : null}
          {running ? (
            <div className="row gap-2">
              <span className="spinner active" />
              <span>Simulating strategy on historical data...</span>
            </div>
          ) : null}
          {result ? (
            <>
              <h3>Backtest Results</h3>
              <div className="glass-2" style={{ padding: 10 }}>
                <EquityChart points={result.equity} />
              </div>
              <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
                <div className="glass-2" style={{ padding: 10, minWidth: 130 }}><div className="text-3 fs-12">Total Return</div><strong>+24.3%</strong></div>
                <div className="glass-2" style={{ padding: 10, minWidth: 130 }}><div className="text-3 fs-12">Max Drawdown</div><strong>-8.2%</strong></div>
                <div className="glass-2" style={{ padding: 10, minWidth: 130 }}><div className="text-3 fs-12">Sharpe Ratio</div><strong>1.84</strong></div>
                <div className="glass-2" style={{ padding: 10, minWidth: 130 }}><div className="text-3 fs-12">Win Rate</div><strong>67%</strong></div>
              </div>
              <div className="glass-2" style={{ padding: 12 }}>
                <div className="section-title">Trade statistics</div>
                <div className="row between fs-13"><span>Total trades</span><strong>{result.stats.total}</strong></div>
                <div className="row between fs-13"><span>Winning trades</span><strong>{result.stats.wins}</strong></div>
                <div className="row between fs-13"><span>Losing trades</span><strong>{result.stats.losses}</strong></div>
                <div className="row between fs-13"><span>Avg profit</span><strong>+$182</strong></div>
                <div className="row between fs-13"><span>Avg loss</span><strong>-$89</strong></div>
              </div>
              <div className="glass-2" style={{ padding: 12 }}>
                <div className="section-title">Monthly returns</div>
                {monthly.map(([m, val]) => (
                  <div key={m} className="row between fs-13" style={{ padding: "4px 0" }}>
                    <span>{m}</span>
                    <span style={{ color: val >= 0 ? "var(--color-green)" : "var(--color-red)" }}>{`${val >= 0 ? "+" : ""}${val.toFixed(1)}%`}</span>
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </article>
      </div>
    </section>
  );
}

