import { useCallback, useEffect, useMemo, useState } from "react";

import client from "../api/client";
import { useBreakpoint } from "../hooks/useBreakpoint";

const SYMBOL_OPTIONS = ["BTC/USD", "ETH/USD", "SOL/USD", "NVDA", "AAPL", "MSFT", "TSLA", "XAU/USD", "OIL/USD"];
const STRATEGY_OPTIONS = ["momentum", "dca", "mean_reversion", "breakout", "grid"];

function EquityChart({ points, initialCapital, startDate, endDate }) {
  const [hoverIndex, setHoverIndex] = useState(null);
  if (!Array.isArray(points) || points.length < 2) return null;
  const width = 960;
  const height = 240;
  const padX = 24;
  const padY = 16;
  const min = Math.min(...points, initialCapital);
  const max = Math.max(...points, initialCapital);
  const range = max - min || 1;
  const stepX = (width - padX * 2) / Math.max(points.length - 1, 1);
  const pointAt = (idx) => {
    const x = padX + idx * stepX;
    const y = height - padY - ((points[idx] - min) / range) * (height - padY * 2);
    return { x, y };
  };
  const lineD = points
    .map((_, idx) => {
      const p = pointAt(idx);
      return `${idx === 0 ? "M" : "L"} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
    })
    .join(" ");
  const areaD = `${lineD} L ${pointAt(points.length - 1).x.toFixed(2)} ${(height - padY).toFixed(2)} L ${pointAt(0).x.toFixed(2)} ${(height - padY).toFixed(2)} Z`;
  const baselineY = height - padY - ((initialCapital - min) / range) * (height - padY * 2);

  const active = hoverIndex === null ? null : { ...pointAt(hoverIndex), value: points[hoverIndex], index: hoverIndex };

  const onMove = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const ratio = Math.max(0, Math.min(1, x / Math.max(bounds.width, 1)));
    const idx = Math.round(ratio * (points.length - 1));
    setHoverIndex(idx);
  };
  const onLeave = () => setHoverIndex(null);

  return (
    <div className="backtest-chart-wrap" onMouseMove={onMove} onMouseLeave={onLeave}>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="240" aria-hidden="true">
        <defs>
          <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="oklch(0.72 0.18 295 / 0.55)" />
            <stop offset="100%" stopColor="oklch(0.72 0.18 295 / 0.05)" />
          </linearGradient>
        </defs>
        <line x1={padX} y1={baselineY} x2={width - padX} y2={baselineY} stroke="oklch(0.62 0.06 250 / 0.7)" strokeDasharray="6 6" />
        <path d={areaD} fill="url(#equityFill)" />
        <path d={lineD} fill="none" stroke="oklch(0.72 0.18 295)" strokeWidth="2.6" strokeLinecap="round" />
        {active ? (
          <>
            <line x1={active.x} y1={padY} x2={active.x} y2={height - padY} stroke="oklch(0.86 0.06 260 / 0.35)" />
            <circle cx={active.x} cy={active.y} r="4" fill="oklch(0.72 0.18 295)" />
          </>
        ) : null}
      </svg>
      {active ? (
        <div className="backtest-tooltip" style={{ left: `${(active.x / width) * 100}%` }}>
          <div>Point #{active.index + 1}</div>
          <strong>${Number(active.value || 0).toLocaleString()}</strong>
        </div>
      ) : null}
      <div className="row between text-3 fs-12" style={{ marginTop: 8 }}>
        <span>{startDate}</span>
        <span>{endDate}</span>
      </div>
    </div>
  );
}

export default function Backtest() {
  const { isDesktop } = useBreakpoint();
  const [form, setForm] = useState({
    symbol: "BTC/USD",
    strategy: "momentum",
    timeframe: "1d",
    startDate: "2024-01-01",
    endDate: "2024-12-31",
    capital: 10000,
    riskLevel: "medium",
  });
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");

  const update = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const runBacktest = async () => {
    setRunning(true);
    setError("");
    try {
      const { data } = await client.post("/api/backtest/run", {
        symbol: form.symbol,
        strategy: form.strategy,
        start_date: form.startDate,
        end_date: form.endDate,
        initial_capital: Number(form.capital),
        timeframe: form.timeframe,
        risk_level: form.riskLevel,
      });
      setResult(data || null);
      const h = await client.get("/api/backtest/history");
      setHistory(Array.isArray(h.data) ? h.data : []);
    } catch (err) {
      setError(err?.response?.data?.error || "Backtest failed.");
    } finally {
      setRunning(false);
    }
  };

  const loadHistory = useCallback(async () => {
    try {
      const { data } = await client.get("/api/backtest/history");
      setHistory(Array.isArray(data) ? data : []);
    } catch {
      setHistory([]);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadHistory();
    }, 0);
    return () => clearTimeout(timer);
  }, [loadHistory]);

  const loadHistoryResult = async (id) => {
    try {
      const { data } = await client.get("/api/backtest/history", { params: { id } });
      if (!data) return;
      setResult({
        final_capital: Number(data.final_capital || 0),
        total_return: Number(data.total_return || 0),
        max_drawdown: Number(data.max_drawdown || 0),
        win_rate: Number(data.win_rate || 0),
        total_trades: Number(data.total_trades || 0),
        winning_trades: Number(data.winning_trades || 0),
        sharpe_ratio: Number(data.sharpe_ratio || 0),
        equity_curve: Array.isArray(data.equity_curve) ? data.equity_curve : [],
        trades_log: Array.isArray(data.trades_log) ? data.trades_log : [],
      });
    } catch {
      setError("Could not load historical result.");
    }
  };

  const exportBacktestCSV = () => {
    if (!result) return;
    const rows = [
      ["Hermes Backtest Export"],
      ["Symbol", form.symbol, "Strategy", form.strategy],
      ["Period", `${form.startDate} to ${form.endDate}`],
      ["Initial Capital", form.capital],
      [""],
      ["RESULTS"],
      ["Total Return", `${Number(result.total_return || 0).toFixed(2)}%`],
      ["Final Capital", `$${Number(result.final_capital || 0).toFixed(2)}`],
      ["Max Drawdown", `${Number(result.max_drawdown || 0).toFixed(2)}%`],
      ["Win Rate", `${Number(result.win_rate || 0).toFixed(2)}%`],
      ["Total Trades", Number(result.total_trades || 0)],
      ["Sharpe Ratio", Number(result.sharpe_ratio || 0).toFixed(3)],
      [""],
      ["TRADES LOG"],
      ["#", "Side", "Price", "P&L", "Return%"],
      ...((result.trades_log || []).map((trade, index) => [
        index + 1,
        trade.side || "",
        Number(trade.price || 0).toFixed(2),
        Number(trade.pnl || 0).toFixed(2),
        Number(trade.return_pct || 0).toFixed(2),
      ])),
      [""],
      ["EQUITY CURVE"],
      ["#", "Equity"],
      ...((result.equity_curve || []).map((value, index) => [index + 1, Number(value || 0).toFixed(2)])),
    ];
    const csv = rows.map((row) => row.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "hermes_backtest.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const metrics = useMemo(() => {
    if (!result) return [];
    return [
      { label: "Total Return", value: `${result.total_return >= 0 ? "+" : ""}${Number(result.total_return || 0).toFixed(2)}%`, tone: Number(result.total_return || 0) >= 0 ? "ok" : "bad" },
      { label: "Final Capital", value: `$${Number(result.final_capital || 0).toLocaleString()}` },
      { label: "Max Drawdown", value: `${Number(result.max_drawdown || 0).toFixed(2)}%` },
      { label: "Win Rate", value: `${Number(result.win_rate || 0).toFixed(2)}%` },
      { label: "Total Trades", value: String(Number(result.total_trades || 0)) },
      { label: "Sharpe Ratio", value: Number(result.sharpe_ratio || 0).toFixed(3) },
    ];
  }, [result]);

  return (
    <section className="page-content">
      <div className={isDesktop ? "row" : "col"} style={{ gap: 16, alignItems: "stretch" }}>
        <article className="glass col gap-3" style={{ padding: 16, flex: isDesktop ? "0 0 380px" : "1 1 auto" }}>
          <h3>Backtest Configuration</h3>
          <label className="col gap-2 fs-12 text-2">
            Symbol
            <select className="bt-field" value={form.symbol} onChange={(e) => update("symbol", e.target.value)}>
              {SYMBOL_OPTIONS.map((symbol) => (
                <option key={symbol} value={symbol}>{symbol}</option>
              ))}
            </select>
          </label>
          <label className="col gap-2 fs-12 text-2">
            Strategy
            <select className="bt-field" value={form.strategy} onChange={(e) => update("strategy", e.target.value)}>
              {STRATEGY_OPTIONS.map((strategy) => (
                <option key={strategy} value={strategy}>{strategy}</option>
              ))}
            </select>
          </label>
          <div className="row gap-2" style={{ flexWrap: "wrap" }}>
            {[
              { id: "1d", label: "1D" },
              { id: "4h", label: "4H" },
              { id: "1h", label: "1H" },
            ].map((timeframe) => (
              <button
                key={timeframe.id}
                type="button"
                className={`pill ${form.timeframe === timeframe.id ? "pill-violet" : "pill-gray"}`}
                style={{ border: "none" }}
                onClick={() => update("timeframe", timeframe.id)}
              >
                {timeframe.label}
              </button>
            ))}
          </div>
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
            <input className="bt-field" type="number" min="100" max="1000000" value={form.capital} onChange={(e) => update("capital", Number(e.target.value))} />
          </label>
          <div className="col gap-2 fs-12 text-2">
            <span>Risk Level</span>
            <div className="row gap-2" style={{ flexWrap: "wrap" }}>
              {["low", "medium", "high"].map((risk) => (
                <button
                  key={risk}
                  type="button"
                  className={`pill ${form.riskLevel === risk ? "pill-violet" : "pill-gray"}`}
                  style={{ border: "none" }}
                  onClick={() => update("riskLevel", risk)}
                >
                  {risk[0].toUpperCase() + risk.slice(1)}
                </button>
              ))}
            </div>
          </div>
          <button
            className="btn"
            type="button"
            style={{ width: "100%", background: "oklch(0.72 0.18 295 / .9)", borderColor: "oklch(0.72 0.18 295 / .9)", color: "#111827" }}
            onClick={runBacktest}
            disabled={running}
          >
            {running ? "Running simulation..." : "▶ Run Backtest"}
          </button>
          {running ? (
            <div className="row gap-2">
              <span className="spinner active" />
              <span>Running simulation...</span>
            </div>
          ) : null}
          {error ? <div className="developer-error">{error}</div> : null}
        </article>

        <article className="glass col gap-3" style={{ padding: 16, flex: 1 }}>
          {!result && !running ? (
            <div className="empty-hint">Run a backtest to generate equity curve and performance metrics.</div>
          ) : null}
          {result ? (
            <>
              <div className="row between" style={{ alignItems: "center" }}>
                <h3 style={{ margin: 0 }}>Backtest Results</h3>
                <button type="button" className="btn btn-ghost" style={{ width: "auto", padding: "10px 12px" }} onClick={exportBacktestCSV}>
                  Export Results (CSV)
                </button>
              </div>
              <div className="backtest-metrics-grid">
                {metrics.map((metric) => (
                  <div key={metric.label} className="glass-2 backtest-metric-card">
                    <div className="text-3 fs-12">{metric.label}</div>
                    <strong className={metric.tone === "ok" ? "backtest-ok" : metric.tone === "bad" ? "backtest-bad" : ""}>{metric.value}</strong>
                  </div>
                ))}
              </div>
              <div className="glass-2" style={{ padding: 12 }}>
                <EquityChart
                  points={Array.isArray(result.equity_curve) ? result.equity_curve : []}
                  initialCapital={Number(form.capital)}
                  startDate={form.startDate}
                  endDate={form.endDate}
                />
              </div>
              <div className="glass-2" style={{ padding: 12 }}>
                <div className="section-title">Recent Trades</div>
                <div className="leaderboard-table-wrap" style={{ overflowX: "auto" }}>
                  <table className="leaderboard-table" style={{ minWidth: 620 }}>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Side</th>
                        <th>Price</th>
                        <th>P&L</th>
                        <th>Return%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(result.trades_log || []).map((trade, idx) => (
                        <tr key={`${trade.i}-${idx}`} className={Number(trade.pnl || 0) >= 0 ? "" : "bt-loss-row"}>
                          <td>{idx + 1}</td>
                          <td>{trade.side}</td>
                          <td>${Number(trade.price || 0).toFixed(2)}</td>
                          <td className={Number(trade.pnl || 0) >= 0 ? "backtest-ok" : "backtest-bad"}>
                            {Number(trade.pnl || 0) >= 0 ? "+" : ""}
                            {Number(trade.pnl || 0).toFixed(2)}
                          </td>
                          <td className={Number(trade.return_pct || 0) >= 0 ? "backtest-ok" : "backtest-bad"}>
                            {Number(trade.return_pct || 0) >= 0 ? "+" : ""}
                            {Number(trade.return_pct || 0).toFixed(2)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="glass-2" style={{ padding: 12 }}>
                <div className="section-title">History</div>
                <div className="backtest-history-list">
                  {history.slice(0, 10).map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="backtest-history-item"
                      onClick={() => loadHistoryResult(item.id)}
                    >
                      <span>
                        {item.symbol} · {item.strategy}
                      </span>
                      <span className={Number(item.total_return || 0) >= 0 ? "backtest-ok" : "backtest-bad"}>
                        {Number(item.total_return || 0) >= 0 ? "+" : ""}
                        {Number(item.total_return || 0).toFixed(2)}%
                      </span>
                      <span className="text-3 fs-12">{String(item.created_at || "").slice(0, 10)}</span>
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : null}
        </article>
      </div>
    </section>
  );
}

