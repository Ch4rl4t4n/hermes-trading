import { useCallback, useEffect, useRef, useState } from "react";
import swarmApi from "../api/swarm";

const POLL_INTERVAL_MS = 15_000;

function buttonClass(status) {
  if (!status) return "swarm-badge swarm-badge-unknown";
  if (!status.redis_ok) return "swarm-badge swarm-badge-down";
  const alive = Number(status?.agents?.alive || 0);
  const unhealthy = Number(status?.agents?.unhealthy || 0);
  if (unhealthy > 0) return "swarm-badge swarm-badge-warn";
  if (alive === 0) return "swarm-badge swarm-badge-warn";
  return "swarm-badge swarm-badge-ok";
}

function statusLabel(status) {
  if (!status) return "…";
  if (!status.redis_ok) return "down";
  return `${Number(status?.agents?.alive || 0)}/${Number(status?.agents?.total || 0)}`;
}

export default function SwarmHealthBadge({ onClick, isAdmin = false }) {
  const [status, setStatus] = useState(null);
  const [open, setOpen] = useState(false);
  const errorReported = useRef(false);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await swarmApi.status();
      setStatus(data || null);
      errorReported.current = false;
    } catch (err) {
      if (!errorReported.current) {
        errorReported.current = true;
        setStatus(null);
      }
    }
  }, []);

  useEffect(() => {
    if (!isAdmin) return undefined;
    fetchStatus();
    const timer = setInterval(fetchStatus, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [fetchStatus, isAdmin]);

  if (!isAdmin) return null;

  const queue = status?.queue || {};

  return (
    <div className="swarm-badge-wrap">
      <button
        type="button"
        className={buttonClass(status)}
        onClick={() => {
          if (onClick) onClick();
          else setOpen((prev) => !prev);
        }}
        title="Swarm v2 health"
      >
        <span className="swarm-badge-dot" />
        <span className="swarm-badge-text">Swarm</span>
        <span className="swarm-badge-count">{statusLabel(status)}</span>
      </button>

      {open && status ? (
        <div className="swarm-badge-popover glass-2">
          <div className="row between">
            <strong>Swarm v2</strong>
            <span className={`pill ${status.redis_ok ? "pill-green" : "pill-red"}`}>
              {status.redis_ok ? "Redis OK" : "Redis DOWN"}
            </span>
          </div>
          <div className="swarm-badge-rows">
            <div><span>Agents alive:</span><strong>{Number(status?.agents?.alive || 0)} / {Number(status?.agents?.total || 0)}</strong></div>
            <div><span>Running:</span><strong>{Number(status?.agents?.running || 0)}</strong></div>
            <div><span>Queue pending:</span><strong>{Number(queue.pending || 0)}</strong></div>
            <div><span>Failed (incl. dead):</span><strong>{Number(queue.failed || 0) + Number(queue.dead || 0)}</strong></div>
          </div>
          <div className="text-3 fs-12">Auto-refresh every 15s</div>
        </div>
      ) : null}
    </div>
  );
}
