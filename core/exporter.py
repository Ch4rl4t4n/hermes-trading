"""CSV/PDF export helpers for Hermes."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from sqlalchemy import text

import core.database as db

PDF_REPORT_TEMPLATE = """
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: Arial, sans-serif; background: #070B14; color: #F0F4FF; padding: 40px; }
.header { display:flex; justify-content:space-between; align-items:center; padding-bottom:24px; border-bottom:2px solid #00D4FF; margin-bottom:24px; }
.logo { font-size: 28px; font-weight: 900; color:#00D4FF; }
.report-date { color: #8B9BB4; font-size: 12px; }
.metrics-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
.metric-card { background:#0D1321; border:1px solid #1E2D45; border-radius:12px; padding:16px; }
.metric-label { color:#8B9BB4; font-size:11px; margin-bottom:4px; }
.metric-value { font-size:22px; font-weight:700; }
.positive { color:#00FF88; } .negative { color:#FF4757; } .neutral { color:#00D4FF; }
.section-title { font-size:16px; font-weight:700; color:#00D4FF; margin-bottom:12px; padding-bottom:8px; border-bottom:1px solid #1E2D45; }
table { width:100%; border-collapse:collapse; font-size:12px; margin-bottom:24px; }
th { background:#0D1321; color:#8B9BB4; padding:8px 10px; text-align:left; font-weight:500; }
td { padding:8px 10px; border-bottom:1px solid #1E2D45; }
.equity-svg { width:100%; height:200px; background:#0D1321; border:1px solid #1E2D45; border-radius:12px; margin-bottom:24px; }
.footer { margin-top:28px; padding-top:14px; border-top:1px solid #1E2D45; color:#4A5568; font-size:10px; text-align:center; }
</style></head>
<body>
<div class="header"><div><div class="logo">HERMES</div><div style="color:#8B9BB4;font-size:12px;">AI Trading Platform</div></div>
<div style="text-align:right;"><div style="font-size:18px;font-weight:700;">{{ report_title }}</div><div class="report-date">Vygenerované: {{ generated_at }}</div><div class="report-date">Obdobie: posledných {{ period_days }} dní</div></div></div>
<div class="metrics-grid">{{ metrics_cards }}</div>
<div class="section-title">Equity Curve</div>
<svg class="equity-svg" viewBox="0 0 800 200" xmlns="http://www.w3.org/2000/svg">{{ equity_svg_path }}</svg>
<div class="section-title">Posledné obchody</div>
<table><thead><tr><th>Dátum</th><th>Čas</th><th>Symbol</th><th>Akcia</th><th>Cena</th><th>P&L USD</th><th>P&L %</th></tr></thead><tbody>{{ trades_rows }}</tbody></table>
<div class="footer">Toto nie je finančné poradenstvo. Minulá výkonnosť nezaručuje budúce výsledky. Hermes — letagentscook.lol</div>
</body></html>
"""


def _engine():
    return db.get_engine()


def _since(period_days: int) -> datetime:
    d = max(1, int(period_days))
    return datetime.now(timezone.utc) - timedelta(days=d)


def _fetch_agent_meta(conn, user_id: int, agent_id: str, agent_type: str) -> dict[str, Any] | None:
    if agent_type == "user":
        row = conn.execute(
            text(
                """
                SELECT id, name, symbol, strategy_type AS strategy, status
                FROM user_agents
                WHERE id = :aid AND user_id = :uid AND status != 'deleted'
                """
            ),
            {"aid": int(agent_id), "uid": int(user_id)},
        ).mappings().first()
        return dict(row) if row else None
    row = conn.execute(
        text(
            """
            SELECT ta.id, ta.name, ta.symbol, ta.strategy, 'active'::text AS status
            FROM user_subscriptions us
            JOIN trading_agents ta ON ta.id = us.agent_id
            WHERE us.user_id = :uid AND us.is_active IS TRUE AND ta.id = :aid
            """
        ),
        {"uid": int(user_id), "aid": str(agent_id)},
    ).mappings().first()
    return dict(row) if row else None


def _fetch_trades(conn, user_id: int, agent_id: str, agent_type: str, period_days: int) -> list[dict[str, Any]]:
    since = _since(period_days)
    if agent_type == "user":
        q = text(
            """
            SELECT timestamp, symbol, action, price, quantity, pnl, reason, confidence
            FROM paper_trades
            WHERE user_id = :uid AND user_agent_id = :aid AND timestamp >= :since
            ORDER BY timestamp DESC
            """
        )
    else:
        q = text(
            """
            SELECT timestamp, symbol, action, price, quantity, pnl, reason, confidence
            FROM paper_trades
            WHERE user_id = :uid AND agent_id = :aid AND timestamp >= :since
            ORDER BY timestamp DESC
            """
        )
    rows = conn.execute(q, {"uid": int(user_id), "aid": agent_id if agent_type == "system" else int(agent_id), "since": since}).mappings().all()
    return [dict(r) for r in rows]


def export_agent_trades_csv(user_id: int, agent_id: str, agent_type: str, period_days: int = 30) -> io.StringIO:
    eng = _engine()
    if eng is None:
        raise RuntimeError("database unavailable")
    with eng.connect() as conn:
        meta = _fetch_agent_meta(conn, user_id, agent_id, agent_type)
        if not meta:
            raise ValueError("Agent not found")
        trades = _fetch_trades(conn, user_id, agent_id, agent_type, period_days)
    out = io.StringIO()
    out.write("\ufeff")
    w = csv.writer(out)
    w.writerow(["Date", "Time", "Symbol", "Action", "Price", "Quantity", "PnL_USD", "PnL_PCT", "Reason", "Confidence", "Agent_Name", "Strategy"])
    for t in trades:
        ts = t.get("timestamp")
        dt = ts if isinstance(ts, datetime) else None
        pnl = float(t.get("pnl") or 0.0)
        notional = float(t.get("price") or 0.0) * float(t.get("quantity") or 0.0) or 1.0
        pnl_pct = (pnl / notional) * 100.0
        w.writerow([
            dt.strftime("%Y-%m-%d") if dt else "",
            dt.strftime("%H:%M:%S") if dt else "",
            t.get("symbol") or "",
            t.get("action") or "",
            float(t.get("price") or 0.0),
            float(t.get("quantity") or 0.0),
            round(pnl, 6),
            round(pnl_pct, 6),
            t.get("reason") or "",
            t.get("confidence") if t.get("confidence") is not None else "",
            meta.get("name") or "",
            meta.get("strategy") or "",
        ])
    out.seek(0)
    return out


def export_agent_performance_csv(user_id: int, agent_id: str, agent_type: str, period_days: int = 30) -> io.StringIO:
    eng = _engine()
    if eng is None:
        raise RuntimeError("database unavailable")
    with eng.connect() as conn:
        meta = _fetch_agent_meta(conn, user_id, agent_id, agent_type)
        if not meta:
            raise ValueError("Agent not found")
        trades = _fetch_trades(conn, user_id, agent_id, agent_type, period_days)
    by_day: dict[str, dict[str, float]] = {}
    for t in trades:
        ts = t.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        d = ts.date().isoformat()
        r = by_day.setdefault(d, {"pnl": 0.0, "trades": 0.0, "wins": 0.0})
        p = float(t.get("pnl") or 0.0)
        r["pnl"] += p
        r["trades"] += 1.0
        if p > 0:
            r["wins"] += 1.0
    out = io.StringIO()
    out.write("\ufeff")
    w = csv.writer(out)
    w.writerow(["Date", "Equity_USD", "PnL_USD", "PnL_PCT", "Trade_Count", "Win_Count", "Win_Rate", "Agent_Name"])
    equity = 10000.0
    for d in sorted(by_day.keys()):
        pnl = by_day[d]["pnl"]
        equity += pnl
        tc = int(by_day[d]["trades"])
        wc = int(by_day[d]["wins"])
        wr = (wc / tc * 100.0) if tc else 0.0
        w.writerow([d, round(equity, 4), round(pnl, 4), round((pnl / 10000.0) * 100.0, 4), tc, wc, round(wr, 4), meta.get("name") or ""])
    out.seek(0)
    return out


def export_portfolio_csv(user_id: int, period_days: int = 30) -> io.StringIO:
    eng = _engine()
    if eng is None:
        raise RuntimeError("database unavailable")
    since = _since(period_days)
    with eng.connect() as conn:
        summary_rows = conn.execute(
            text(
                """
                SELECT ua.id::text AS aid, ua.name, ua.symbol, ua.strategy_type AS strategy, ua.status
                FROM user_agents ua
                WHERE ua.user_id = :uid AND ua.status != 'deleted'
                """
            ),
            {"uid": int(user_id)},
        ).mappings().all()
        trades = conn.execute(
            text(
                """
                SELECT timestamp, symbol, action, price, pnl, COALESCE(ua.name, ta.name, 'Unknown') AS agent_name
                FROM paper_trades pt
                LEFT JOIN user_agents ua ON pt.user_agent_id = ua.id
                LEFT JOIN trading_agents ta ON pt.agent_id = ta.id
                WHERE pt.user_id = :uid AND pt.timestamp >= :since
                ORDER BY pt.timestamp DESC
                """
            ),
            {"uid": int(user_id), "since": since},
        ).mappings().all()
    summary_df = pd.DataFrame([dict(r) for r in summary_rows])
    if not summary_df.empty:
        perf = {}
        for r in trades:
            nm = str(r.get("agent_name") or "")
            d = perf.setdefault(nm, {"pnl": 0.0, "trades": 0, "wins": 0})
            p = float(r.get("pnl") or 0.0)
            d["pnl"] += p
            d["trades"] += 1
            if p > 0:
                d["wins"] += 1
        total_pnl = []
        total_pct = []
        wr = []
        tc = []
        for _, rr in summary_df.iterrows():
            nm = str(rr["name"])
            d = perf.get(nm, {"pnl": 0.0, "trades": 0, "wins": 0})
            total_pnl.append(round(d["pnl"], 4))
            total_pct.append(round((d["pnl"] / 10000.0) * 100.0, 4))
            tc.append(d["trades"])
            wr.append(round((d["wins"] / d["trades"] * 100.0), 4) if d["trades"] else 0.0)
        summary_df["Total_PnL_USD"] = total_pnl
        summary_df["Total_PnL_PCT"] = total_pct
        summary_df["Win_Rate"] = wr
        summary_df["Trade_Count"] = tc
        summary_df.rename(columns={"name": "Agent_Name", "symbol": "Symbol", "strategy": "Strategy", "status": "Status"}, inplace=True)
    trades_df = pd.DataFrame([dict(x) for x in trades])
    out = io.StringIO()
    out.write("\ufeff")
    w = csv.writer(out)
    w.writerow(["Sheet", "Summary"])
    if summary_df.empty:
        w.writerow(["", "No data"])
    else:
        w.writerow(list(summary_df.columns))
        for _, rr in summary_df.iterrows():
            w.writerow([rr.get(c) for c in summary_df.columns])
    w.writerow([])
    w.writerow(["Sheet", "All Trades"])
    if trades_df.empty:
        w.writerow(["", "No data"])
    else:
        cols = ["timestamp", "agent_name", "symbol", "action", "price", "pnl"]
        w.writerow(["Date", "Time", "Agent_Name", "Symbol", "Action", "Price", "PnL_USD"])
        for _, rr in trades_df.iterrows():
            ts = rr.get("timestamp")
            dt = ts if isinstance(ts, datetime) else None
            w.writerow([
                dt.strftime("%Y-%m-%d") if dt else "",
                dt.strftime("%H:%M:%S") if dt else "",
                rr.get("agent_name") or "",
                rr.get("symbol") or "",
                rr.get("action") or "",
                rr.get("price") or 0,
                rr.get("pnl") or 0,
            ])
    out.seek(0)
    return out


def build_equity_svg_path(equity_curve: list[dict[str, Any]]) -> str:
    if not equity_curve or len(equity_curve) < 2:
        return '<text x="400" y="100" fill="#8B9BB4" text-anchor="middle">Nedostatok dát</text>'
    values = [float(p.get("equity") or 0.0) for p in equity_curve]
    min_val = min(values)
    max_val = max(values)
    val_range = max_val - min_val or 1.0
    pts = []
    for i, val in enumerate(values):
        x = (i / (len(values) - 1)) * 760 + 20
        y = 180 - ((val - min_val) / val_range) * 160 + 10
        pts.append(f"{x:.1f},{y:.1f}")
    color = "#00FF88" if values[-1] >= values[0] else "#FF4757"
    return f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2"/>'


def _render_metrics_cards(metrics: list[tuple[str, str, str]]) -> str:
    parts = []
    for label, value, cls in metrics:
        parts.append(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value {cls}">{value}</div></div>')
    return "".join(parts)


def _render_trade_rows(trades: list[dict[str, Any]]) -> str:
    rows = []
    for t in trades[:50]:
        ts = t.get("timestamp")
        dt = ts if isinstance(ts, datetime) else None
        p = float(t.get("pnl") or 0.0)
        notional = float(t.get("price") or 0.0) * float(t.get("quantity") or 0.0) or 1.0
        pct = (p / notional) * 100.0
        rows.append(
            "<tr>"
            f"<td>{dt.strftime('%Y-%m-%d') if dt else ''}</td>"
            f"<td>{dt.strftime('%H:%M:%S') if dt else ''}</td>"
            f"<td>{t.get('symbol') or ''}</td>"
            f"<td>{t.get('action') or ''}</td>"
            f"<td>{float(t.get('price') or 0.0):.4f}</td>"
            f"<td>{p:.4f}</td>"
            f"<td>{pct:.4f}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='7'>No trades</td></tr>"


def _safe_weasyprint_pdf(html_content: str) -> bytes:
    try:
        from weasyprint import HTML  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("WeasyPrint nie je dostupný") from exc
    return HTML(string=html_content).write_pdf()


def generate_agent_pdf_report(user_id: int, agent_id: str, agent_type: str, period_days: int = 30) -> bytes:
    eng = _engine()
    if eng is None:
        raise RuntimeError("database unavailable")
    with eng.connect() as conn:
        meta = _fetch_agent_meta(conn, user_id, agent_id, agent_type)
        if not meta:
            raise ValueError("Agent not found")
        trades = _fetch_trades(conn, user_id, agent_id, agent_type, period_days)
    pnl = sum(float(t.get("pnl") or 0.0) for t in trades)
    tc = len(trades)
    wins = sum(1 for t in trades if float(t.get("pnl") or 0.0) > 0)
    wr = (wins / tc * 100.0) if tc else 0.0
    eq = 10000.0
    eq_curve = [{"equity": eq}]
    peak = eq
    max_dd = 0.0
    for t in reversed(trades):
        eq += float(t.get("pnl") or 0.0)
        peak = max(peak, eq)
        dd = (1.0 - eq / peak) * 100.0 if peak else 0.0
        max_dd = max(max_dd, dd)
        eq_curve.append({"equity": eq})
    svg = build_equity_svg_path(eq_curve)
    html_content = (
        PDF_REPORT_TEMPLATE.replace("{{ report_title }}", f"Agent Report — {meta.get('name') or 'Agent'}")
        .replace("{{ generated_at }}", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        .replace("{{ period_days }}", str(int(period_days)))
        .replace(
            "{{ metrics_cards }}",
            _render_metrics_cards(
                [
                    ("Celkový P&L", f"{pnl:+.2f} USD", "positive" if pnl >= 0 else "negative"),
                    ("Win Rate", f"{wr:.2f}%", "neutral"),
                    ("Max Drawdown", f"-{max_dd:.2f}%", "negative"),
                    ("Obchody", str(tc), "neutral"),
                ]
            ),
        )
        .replace("{{ equity_svg_path }}", svg)
        .replace("{{ trades_rows }}", _render_trade_rows(trades))
    )
    return _safe_weasyprint_pdf(html_content)


def generate_portfolio_pdf_report(user_id: int, period_days: int = 30) -> bytes:
    eng = _engine()
    if eng is None:
        raise RuntimeError("database unavailable")
    since = _since(period_days)
    with eng.connect() as conn:
        trades = conn.execute(
            text(
                """
                SELECT timestamp, symbol, action, price, quantity, pnl,
                       COALESCE(ua.name, ta.name, 'Unknown') AS agent_name
                FROM paper_trades pt
                LEFT JOIN user_agents ua ON pt.user_agent_id = ua.id
                LEFT JOIN trading_agents ta ON pt.agent_id = ta.id
                WHERE pt.user_id = :uid AND pt.timestamp >= :since
                ORDER BY pt.timestamp DESC
                """
            ),
            {"uid": int(user_id), "since": since},
        ).mappings().all()
    pnl = sum(float(t.get("pnl") or 0.0) for t in trades)
    tc = len(trades)
    wins = sum(1 for t in trades if float(t.get("pnl") or 0.0) > 0)
    wr = (wins / tc * 100.0) if tc else 0.0
    by_agent = {}
    for t in trades:
        nm = str(t.get("agent_name") or "Unknown")
        d = by_agent.setdefault(nm, 0.0)
        by_agent[nm] = d + float(t.get("pnl") or 0.0)
    best = max(by_agent.items(), key=lambda x: x[1])[0] if by_agent else "—"
    eq = 10000.0
    eq_curve = [{"equity": eq}]
    for t in reversed(trades):
        eq += float(t.get("pnl") or 0.0)
        eq_curve.append({"equity": eq})
    svg = build_equity_svg_path(eq_curve)
    rows = []
    for t in trades[:20]:
        ts = t.get("timestamp")
        dt = ts if isinstance(ts, datetime) else None
        p = float(t.get("pnl") or 0.0)
        rows.append(
            f"<tr><td>{dt.strftime('%Y-%m-%d') if dt else ''}</td><td>{dt.strftime('%H:%M:%S') if dt else ''}</td><td>{t.get('agent_name') or ''}</td><td>{t.get('symbol') or ''}</td><td>{t.get('action') or ''}</td><td>{float(t.get('price') or 0.0):.4f}</td><td>{p:.4f}</td></tr>"
        )
    table_html = (
        "<table><thead><tr><th>Dátum</th><th>Čas</th><th>Agent</th><th>Symbol</th><th>Akcia</th><th>Cena</th><th>P&L USD</th></tr></thead>"
        f"<tbody>{''.join(rows) or '<tr><td colspan=7>No trades</td></tr>'}</tbody></table>"
    )
    html_content = (
        PDF_REPORT_TEMPLATE.replace("{{ report_title }}", "Portfolio Report")
        .replace("{{ generated_at }}", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        .replace("{{ period_days }}", str(int(period_days)))
        .replace(
            "{{ metrics_cards }}",
            _render_metrics_cards(
                [
                    ("Celkový P&L", f"{pnl:+.2f} USD", "positive" if pnl >= 0 else "negative"),
                    ("Počet agentov", str(len(by_agent)), "neutral"),
                    ("Win Rate", f"{wr:.2f}%", "neutral"),
                    ("Best performer", best, "neutral"),
                ]
            ),
        )
        .replace("{{ equity_svg_path }}", svg)
        .replace("{{ trades_rows }}", "".join(rows) or "<tr><td colspan='7'>No trades</td></tr>")
    )
    # append broader table section for recent cross-agent trades
    html_content = html_content.replace("</body></html>", "<div class='section-title'>Posledných 20 trades naprieč všetkými agentmi</div>" + table_html + "</body></html>")
    return _safe_weasyprint_pdf(html_content)
