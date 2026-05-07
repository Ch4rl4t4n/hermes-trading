export default function OnboardingChecklist({ steps }) {
  const done = steps.filter((s) => s.done).length;
  const total = steps.length || 1;
  const pct = Math.round((done / total) * 100);

  return (
    <div className="onb-checklist">
      <div className="onb-cl-header">
        <strong>Onboarding</strong>
      </div>
      <div className="onb-cl-progress-bar">
        <div className="onb-cl-progress-fill" style={{ width: `${pct}%` }} />
      </div>
      {steps.map((item) => (
        <div key={item.key} className={`onb-cl-item ${item.done ? "done" : ""}`}>
          <div className="onb-cl-check">{item.done ? "✓" : ""}</div>
          <span>{item.label}</span>
        </div>
      ))}
      <div className="onb-cl-count">
        {done} / {total} completed
      </div>
    </div>
  );
}
