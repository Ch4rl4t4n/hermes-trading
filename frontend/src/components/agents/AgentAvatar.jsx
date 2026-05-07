const SIZE_MAP = {
  sm: 32,
  md: 48,
  lg: 96,
};

function initialsFromName(name) {
  const parts = String(name || "Agent").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
}

function hashToGradient(name) {
  const text = String(name || "agent");
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) | 0;
  const h1 = Math.abs(hash) % 360;
  const h2 = (h1 + 70) % 360;
  return `linear-gradient(135deg, oklch(0.62 0.14 ${h1}), oklch(0.68 0.16 ${h2}))`;
}

export default function AgentAvatar({ name, level = 1, skin = "basic", size = "md" }) {
  const px = SIZE_MAP[size] || SIZE_MAP.md;
  const style = {
    width: px,
    height: px,
    minWidth: px,
    minHeight: px,
    fontSize: size === "lg" ? 22 : size === "md" ? 14 : 11,
  };

  const initials = initialsFromName(name);
  const basicBg = hashToGradient(name);
  const skinClass = `agent-avatar agent-avatar-${skin}`;

  return (
    <div className={skinClass} style={{ ...style, background: skin === "basic" ? basicBg : undefined }} aria-label={`${name} avatar level ${level}`}>
      {skin === "meme_cat" ? <span className="agent-avatar-emoji">🐱</span> : null}
      {skin === "wolf" ? <span className="agent-avatar-emoji">🐺</span> : null}
      {skin === "cosmic" ? <span className="agent-avatar-emoji">✨</span> : null}
      {skin === "neon" ? <span className="agent-avatar-circuit" aria-hidden="true" /> : null}
      {skin === "basic" || skin === "neon" ? <span className="agent-avatar-initials">{initials}</span> : null}
    </div>
  );
}
