import { useState } from "react";
import AgentCardCompact from "../agents/AgentCardCompact";

/**
 * One category block (CRYPTO / STOCKS / COMMODITIES) with:
 *   - header with active count and `+ ADD`
 *   - drag-and-drop reorderable grid of agent cards
 *   - "+ add …" placeholders for unused slots up to `max`
 */

export default function CategorySection({
  title,
  used,
  max,
  agents,
  emptyLabel,
  onToggleAgent,
  onShare,
  onDetails,
  onExport,
  onRemove,
  onReorder,
  onAddAgent,
}) {
  const [draggingId, setDraggingId] = useState(null);
  const [overId, setOverId] = useState(null);
  const placeholders = Math.max(0, max - agents.length);

  const handleDragStart = (id) => (ev) => {
    setDraggingId(id);
    if (ev?.dataTransfer) {
      try {
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(id));
      } catch {
        /* noop */
      }
    }
  };

  const handleDragOver = (id) => (ev) => {
    ev.preventDefault();
    if (ev?.dataTransfer) ev.dataTransfer.dropEffect = "move";
    if (overId !== id) setOverId(id);
  };

  const handleDragLeave = (id) => () => {
    if (overId === id) setOverId(null);
  };

  const handleDrop = (targetId) => (ev) => {
    ev.preventDefault();
    if (!draggingId || draggingId === targetId) {
      setDraggingId(null);
      setOverId(null);
      return;
    }
    const fromIdx = agents.findIndex((a) => (a.id || a.symbol) === draggingId);
    const toIdx = agents.findIndex((a) => (a.id || a.symbol) === targetId);
    if (fromIdx >= 0 && toIdx >= 0) {
      const next = agents.slice();
      const [moved] = next.splice(fromIdx, 1);
      next.splice(toIdx, 0, moved);
      onReorder?.(next.map((a) => a.id || a.symbol));
    }
    setDraggingId(null);
    setOverId(null);
  };

  const handleDragEnd = () => {
    setDraggingId(null);
    setOverId(null);
  };

  return (
    <section className="hermes-category">
      <header className="hermes-category-head">
        <span className="hermes-category-title">{title}</span>
        <div className="hermes-category-meta">
          <span className="hermes-category-count">{used} active</span>
          <button type="button" className="hermes-category-add" onClick={onAddAgent}>
            + ADD
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M7 17 17 7M9 7h8v8" />
            </svg>
          </button>
        </div>
      </header>

      <div className="hermes-category-grid">
        {agents.map((agent) => {
          const id = agent.id || agent.symbol;
          return (
            <AgentCardCompact
              key={id}
              agent={agent}
              draggable
              isDragging={draggingId === id}
              isDragOver={overId === id && draggingId !== id}
              onDragStart={handleDragStart(id)}
              onDragOver={handleDragOver(id)}
              onDragLeave={handleDragLeave(id)}
              onDrop={handleDrop(id)}
              onDragEnd={handleDragEnd}
              onToggle={() => onToggleAgent?.(agent.symbol || agent.id)}
              onDetails={() => onDetails?.(agent)}
              onShare={() => onShare?.(agent)}
              onExport={() => onExport?.(agent)}
              onRemove={() => onRemove?.(agent)}
            />
          );
        })}
        {Array.from({ length: placeholders }).map((_, i) => (
          <button
            key={`ph-${i}`}
            type="button"
            className="hermes-slot-placeholder"
            onClick={onAddAgent}
            aria-label={emptyLabel}
          >
            <span className="hermes-slot-placeholder-icon" aria-hidden="true">
              <svg viewBox="0 0 16 16" width="14" height="14" focusable="false">
                <path
                  d="M8 3v10M3 8h10"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <span>{emptyLabel}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
