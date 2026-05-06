import yaml
from datetime import time as dtime
from pathlib import Path

from agents.base_agent import AgentConfig


def load_agent_config(path: Path) -> AgentConfig:
    with open(path) as f:
        d = yaml.safe_load(f) or {}
    if not isinstance(d, dict):
        raise ValueError(f"invalid yaml in {path}")
    return _agent_config_from_mapping(d)


def _agent_config_from_mapping(d: dict) -> AgentConfig:
    schedule = d.get("schedule", {}) or {}
    rule = d.get("rule_based", {}) or {}
    llm = d.get("llm", {}) or {}
    risk = d.get("risk", {}) or {}

    def parse_time(t: str) -> dtime:
        h, m = t.split(":")
        return dtime(int(h), int(m))

    active_hours = schedule.get("active_hours", "00:00-23:59")
    start_str, end_str = active_hours.split("-")

    return AgentConfig(
        name=d["name"],
        symbol=d["symbol"],
        asset_type=d["asset_type"],
        enabled=d.get("enabled", True),
        trade_usd=float(d["trade_usd"]),
        timezone=schedule.get("timezone", "UTC"),
        active_hours_start=parse_time(start_str),
        active_hours_end=parse_time(end_str),
        check_interval_seconds=int(schedule.get("check_interval_seconds", 60)),
        rsi_period=int(rule.get("rsi_period", 14)),
        rsi_buy_threshold=float(rule.get("rsi_buy_threshold", 35)),
        rsi_sell_threshold=float(rule.get("rsi_sell_threshold", 65)),
        macd_enabled=bool(rule.get("macd_enabled", True)),
        signal_confidence_threshold=float(rule.get("signal_confidence_threshold", 0.60)),
        llm_enabled=bool(llm.get("enabled", False)),
        llm_trigger_threshold=float(llm.get("trigger_threshold", 0.65)),
        llm_model=llm.get("model", "haiku"),
        llm_max_calls_per_hour=int(llm.get("max_calls_per_hour", 6)),
        llm_use_sonnet_above=float(llm.get("use_sonnet_above", 0.85)),
        trailing_stop_pct=float(risk.get("trailing_stop_pct", 3.0)),
        take_profit_pct=float(risk.get("take_profit_pct", 6.0)),
        max_trades_per_day=int(risk.get("max_trades_per_day", 10)),
        max_daily_loss_pct=float(risk.get("max_daily_loss_pct", 2.0)),
        max_position_pct=float(risk.get("max_position_pct", 0.06)),
        timeframe=schedule.get("timeframe", "1m"),
        trailing_activate_pct=float(risk.get("trailing_activate_pct", 0.0)),
        atr_position_sizing=bool(risk.get("atr_position_sizing", False)),
        trading_mode=str(d.get("trading_mode", "day_trading")),
        dca=dict(d.get("dca") or {}),
        grid=dict(d.get("grid") or {}),
        scheduled_orders=list(d.get("scheduled_orders") or []),
        take_profit_scaled=dict(d.get("take_profit") or {}),
    )


def agent_config_from_dict(d: dict) -> AgentConfig:
    """Build AgentConfig from an in-memory YAML-shaped dict (DB JSON blob)."""
    return _agent_config_from_mapping(d)


def load_all_agents(config_dir: Path) -> list[AgentConfig]:
    configs = []
    for yaml_file in sorted(config_dir.glob("*.yaml")):
        try:
            cfg = load_agent_config(yaml_file)
            if cfg.enabled:
                configs.append(cfg)
        except Exception as exc:
            print(f"[config_loader] ERROR loading {yaml_file.name}: {exc}")
    return configs
