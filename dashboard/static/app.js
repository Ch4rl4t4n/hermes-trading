console.log('Babel starting');

// Hermes Trading Platform — Interactive Prototype
const { useState, useEffect, useRef, useMemo, useCallback } = React;

// ============ ICONS ============
const Icon = ({ name, size = 16, ...props }) => {
  const paths = {
    dashboard: <><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></>,
    market: <><path d="M3 3h4l2.5 13h9L21 7H7"/><circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>,
    bell: <><path d="M6 9a6 6 0 0 1 12 0c0 4 1.5 5.5 2 6.5H4c.5-1 2-2.5 2-6.5z"/><path d="M10 19a2 2 0 0 0 4 0"/></>,
    bolt: <><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/></>,
    search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></>,
    chevron: <><path d="m9 6 6 6-6 6"/></>,
    chevDown: <><path d="m6 9 6 6 6-6"/></>,
    arrowUp: <><path d="M12 19V5M5 12l7-7 7 7"/></>,
    arrowDown: <><path d="M12 5v14M19 12l-7 7-7-7"/></>,
    user: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
    users: <><circle cx="9" cy="8" r="4"/><path d="M2 21a7 7 0 0 1 14 0"/><circle cx="17" cy="8" r="3"/><path d="M22 21a6 6 0 0 0-5-5.9"/></>,
    trophy: <><path d="M8 4h8v6a4 4 0 0 1-8 0V4z"/><path d="M16 6h3v2a3 3 0 0 1-3 3M8 6H5v2a3 3 0 0 0 3 3"/><path d="M9 18h6M12 14v4M9 21h6"/></>,
    bot: <><rect x="4" y="6" width="16" height="13" rx="3"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><path d="M12 2v4M9 19v3M15 19v3"/></>,
    chart: <><path d="M3 3v18h18"/><path d="m7 14 4-5 3 3 5-6"/></>,
    lock: <><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></>,
    mail: <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></>,
    pause: <><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></>,
    play: <><path d="M7 4v16l13-8z"/></>,
    trash: <><path d="M4 7h16M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"/></>,
    share: <><circle cx="6" cy="12" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M8.6 10.5l6.8-3M8.6 13.5l6.8 3"/></>,
    copy: <><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></>,
    code: <><path d="m8 6-6 6 6 6M16 6l6 6-6 6M14 4l-4 16"/></>,
    flag: <><path d="M4 21V4M4 5h13l-2 4 2 4H4"/></>,
    check: <><path d="M5 12l4 4 10-10"/></>,
    x: <><path d="M6 6l12 12M18 6L6 18"/></>,
    google: <><path fill="#fff" d="M21 12.2c0-.7-.06-1.4-.18-2H12v3.8h5.05a4.3 4.3 0 0 1-1.87 2.83v2.35h3.03c1.77-1.63 2.79-4.04 2.79-6.98z"/><path fill="#fff" d="M12 21c2.52 0 4.64-.83 6.18-2.27l-3.03-2.35a5.4 5.4 0 0 1-3.15.9 5.4 5.4 0 0 1-5.07-3.74H3.81v2.43A9 9 0 0 0 12 21z" opacity=".7"/><path fill="#fff" d="M6.93 13.54a5.4 5.4 0 0 1 0-3.08V8.03H3.81a9 9 0 0 0 0 8.06l3.12-2.55z" opacity=".5"/><path fill="#fff" d="M12 6.6c1.37 0 2.6.47 3.57 1.4l2.68-2.68A9 9 0 0 0 12 3a9 9 0 0 0-8.19 5.03l3.12 2.43A5.4 5.4 0 0 1 12 6.6z" opacity=".3"/></>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...props}>
      {paths[name]}
    </svg>
  );
};

// ============ DATA ============
const DEMO_AGENTS = [
  { id: 1, symbol: 'BTC/USD', name: 'BTC Momentum Hunter', category: 'crypto', win: 67, pnl: 234, status: 'live', strategy: 'Momentum', risk: 'medium', trades: 142, sparks: [12, 14, 13, 18, 22, 21, 28, 31, 29, 34, 38, 42] },
  { id: 2, symbol: 'ETH/USD', name: 'ETH DCA Compounder', category: 'crypto', win: 72, pnl: 56, status: 'live', strategy: 'DCA', risk: 'low', trades: 88, sparks: [4, 6, 5, 8, 10, 9, 12, 13, 12, 14, 15, 16] },
  { id: 3, symbol: 'NVDA', name: 'NVDA Momentum', category: 'stocks', win: 69, pnl: 89, status: 'live', strategy: 'Momentum', risk: 'medium', trades: 64, sparks: [10, 11, 9, 14, 16, 15, 18, 22, 20, 24, 26, 28] },
  { id: 4, symbol: 'ETH/USD', name: 'ETH Mean Reversion', category: 'crypto', win: 54, pnl: -12, status: 'paused', strategy: 'Mean Rev', risk: 'high', trades: 38, sparks: [8, 7, 9, 6, 5, 7, 4, 3, 5, 4, 2, 1] },
];

const MARKETPLACE_AGENTS = [
  { id: 'm1', symbol: 'BTC/USD', name: 'Apex Sniper', author: 'Hermes Labs', subs: 4821, win: 71, monthlyPnl: 18.3, badge: 'top_gainer', strategy: 'Breakout', verified: true },
  { id: 'm2', symbol: 'SOL/USD', name: 'Solana Surge', author: 'Hermes Labs', subs: 3104, win: 68, monthlyPnl: 24.6, badge: 'hot_streak', strategy: 'Momentum', verified: true },
  { id: 'm3', symbol: 'ETH/USD', name: 'Steady Compounder', author: 'Hermes Labs', subs: 2890, win: 64, monthlyPnl: 9.4, badge: 'steady', strategy: 'DCA', verified: true },
  { id: 'm4', symbol: 'BTC/USD', name: 'Volatility Tamer', author: 'm.kovac', subs: 1248, win: 73, monthlyPnl: 12.7, badge: 'reliable', strategy: 'Mean Rev', verified: false },
  { id: 'm5', symbol: 'AVAX/USD', name: 'Avalanche Hunter', author: 'cryptojano', subs: 842, win: 62, monthlyPnl: 31.2, badge: 'top_gainer', strategy: 'Momentum', verified: false },
  { id: 'm6', symbol: 'LINK/USD', name: 'Oracle Edge', author: 'p.novak', subs: 612, win: 58, monthlyPnl: 7.8, badge: null, strategy: 'Grid', verified: false },
];

const LEADERBOARD = [
  { rank: 1, user: 'crypto_jano', tier: 'elite', pnl: 12480, win: 71, trades: 284, agents: 8, change: 0 },
  { rank: 2, user: 'm.kovac', tier: 'elite', pnl: 9870, win: 68, trades: 312, agents: 12, change: 1 },
  { rank: 3, user: 'satoshi_sk', tier: 'pro', pnl: 8240, win: 73, trades: 198, agents: 6, change: -1 },
  { rank: 4, user: 'p.novak', tier: 'pro', pnl: 7120, win: 65, trades: 240, agents: 5, change: 2 },
  { rank: 5, user: 'jc.demo', tier: 'pro', pnl: 367, win: 67, trades: 142, agents: 4, change: 0, isMe: true },
  { rank: 6, user: 'tradergirl', tier: 'pro', pnl: 5980, win: 62, trades: 156, agents: 4, change: -2 },
  { rank: 7, user: 'volatility', tier: 'basic', pnl: 4210, win: 58, trades: 98, agents: 3, change: 1 },
  { rank: 8, user: 'mean_rev', tier: 'pro', pnl: 3840, win: 71, trades: 76, agents: 4, change: 0 },
];

const ADMIN_USERS = [
  { id: 1, email: 'crypto.jano@gmail.com', handle: 'crypto_jano', tier: 'elite', status: 'active', joined: '2024-08-12', agents: 8, pnl: 12480, lastSeen: 'pred 2 min', verified: true },
  { id: 2, email: 'martin.kovac@email.sk', handle: 'm.kovac', tier: 'elite', status: 'active', joined: '2024-09-04', agents: 12, pnl: 9870, lastSeen: 'pred 14 min', verified: true },
  { id: 3, email: 'satoshi@protonmail.com', handle: 'satoshi_sk', tier: 'pro', status: 'active', joined: '2024-10-18', agents: 6, pnl: 8240, lastSeen: 'pred 1 h', verified: true },
  { id: 4, email: 'pavol.novak@firma.sk', handle: 'p.novak', tier: 'pro', status: 'active', joined: '2024-11-02', agents: 5, pnl: 7120, lastSeen: 'pred 3 h', verified: false },
  { id: 5, email: 'demo@hermes.app', handle: 'jc.demo', tier: 'pro', status: 'active', joined: '2025-01-22', agents: 4, pnl: 367, lastSeen: 'online', verified: true },
  { id: 6, email: 'lucia.t@gmail.com', handle: 'tradergirl', tier: 'pro', status: 'active', joined: '2025-02-14', agents: 4, pnl: 5980, lastSeen: 'pred 2 dni', verified: true },
  { id: 7, email: 'volatility.king@gmail.com', handle: 'volatility', tier: 'basic', status: 'active', joined: '2025-03-08', agents: 3, pnl: 4210, lastSeen: 'pred 6 h', verified: false },
  { id: 8, email: 'mean.rev@email.sk', handle: 'mean_rev', tier: 'pro', status: 'suspended', joined: '2025-03-15', agents: 4, pnl: 3840, lastSeen: 'pred 5 dni', verified: true, suspendReason: 'Spam reports' },
  { id: 9, email: 'spam.acc@temp.com', handle: 'spammer42', tier: 'basic', status: 'banned', joined: '2025-04-01', agents: 0, pnl: 0, lastSeen: 'banned', verified: false, suspendReason: 'Múltiple ToS violations' },
  { id: 10, email: 'tomas.h@gmail.com', handle: 't.horvath', tier: 'basic', status: 'pending', joined: '2026-05-04', agents: 0, pnl: 0, lastSeen: 'nikdy', verified: false },
];

const TRADES = [
  { time: '11:42', symbol: 'BTC/USD', agent: 'BTC Momentum Hunter', side: 'BUY', price: 71240, qty: 0.012, pnl: null, status: 'open' },
  { time: '11:18', symbol: 'NVDA', agent: 'NVDA Momentum', side: 'SELL', price: 1284, qty: 0.5, pnl: 24, status: 'closed' },
  { time: '10:54', symbol: 'ETH/USD', agent: 'ETH DCA Compounder', side: 'BUY', price: 3892, qty: 0.05, pnl: null, status: 'open' },
  { time: '09:22', symbol: 'BTC/USD', agent: 'BTC Momentum Hunter', side: 'SELL', price: 70980, qty: 0.018, pnl: 142, status: 'closed' },
  { time: '08:08', symbol: 'ETH/USD', agent: 'ETH Mean Reversion', side: 'SELL', price: 3902, qty: 0.04, pnl: -12, status: 'closed' },
  { time: '07:36', symbol: 'NVDA', agent: 'NVDA Momentum', side: 'BUY', price: 1268, qty: 0.5, pnl: null, status: 'open' },
];

const SYMBOLS = {
  crypto: ['BTC/USD','ETH/USD','SOL/USD','AVAX/USD','LINK/USD','DOGE/USD','ADA/USD','MATIC/USD'],
  stocks: ['NVDA','AAPL','MSFT','TSLA','AMZN','META','GOOGL'],
  commodities: ['XAU/USD (Gold)','XAG/USD (Silver)','OIL/USD','NG/USD']
};
const STRATEGIES = [
  { id: 'momentum', label: 'Momentum', desc: 'Nakupuje pri prelomenom resistance, predáva pri slabnúcom trende' },
  { id: 'dca', label: 'DCA Compounder', desc: 'Pravidelné nákupy v intervaloch, reinvestuje zisky' },
  { id: 'meanrev', label: 'Mean Reversion', desc: 'Nakupuje na lokálnych dnách, predáva pri návrate k priemeru' },
  { id: 'breakout', label: 'Breakout', desc: 'Hľadá konsolidáciu a vstupuje pri prelomenom kanáli' },
  { id: 'grid', label: 'Grid Trading', desc: 'Postavená sieť bid/ask, profituje z bočného trhu' },
];

// ============ HELPERS ============
const fmtMoney = (n) => (n >= 0 ? '+' : '') + '$' + Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
const fmtPct = (n) => (n >= 0 ? '+' : '') + n.toFixed(1) + '%';

function Sparkline({ data, color = 'oklch(0.78 0.16 155)', width = 80, height = 24, animate = true }) {
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * (height - 4) - 2}`).join(' ');
  return (
    <svg className="spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <polyline className={animate ? 'spark-path' : ''} points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AnimatedNumber({ value, prefix = '', suffix = '', duration = 800, decimals = 0 }) {
  const [display, setDisplay] = useState(value);
  const prevRef = useRef(value);
  useEffect(() => {
    const start = prevRef.current;
    const delta = value - start;
    if (Math.abs(delta) < 0.01) { setDisplay(value); return; }
    let raf;
    const t0 = performance.now();
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(start + delta * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
      else prevRef.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  const sign = display >= 0 ? '+' : '';
  return <span className="mono">{prefix}{value < 0 ? '-' : (prefix.includes('$') || prefix.includes('+') ? '' : '')}{prefix.includes('$') ? '' : sign}{Math.abs(display).toLocaleString('en-US', { maximumFractionDigits: decimals, minimumFractionDigits: decimals })}{suffix}</span>;
}

function MoneyTick({ value, big = false }) {
  const [v, setV] = useState(value);
  const [flash, setFlash] = useState(null);
  useEffect(() => {
    if (value !== v) {
      setFlash(value > v ? 'up' : 'down');
      setV(value);
      const t = setTimeout(() => setFlash(null), 500);
      return () => clearTimeout(t);
    }
  }, [value]);
  const cls = `mono ${value >= 0 ? 'num-up' : 'num-down'} ${flash === 'up' ? 'tick-up' : flash === 'down' ? 'tick-down' : ''}`;
  return <span className={cls} style={{ fontSize: big ? 48 : undefined, fontWeight: big ? 700 : 600 }}>
    {value >= 0 ? '+' : '-'}${Math.abs(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}
  </span>;
}

// ============ TOP NAV ============
function TopNav({ page, onNav, isAdmin, onLogout, user, notifCount }) {
  const links = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'marketplace', label: 'Marketplace' },
    { id: 'builder', label: 'Builder' },
    { id: 'leaderboard', label: 'Leaderboard' },
    { id: 'backtest', label: 'Backtesting' },
  ];
  return (
    <nav className="topnav">
      <div className="brand">
        <div className="brand-mark">H</div>
        <span>HERMES</span>
        <span className="pill pill-amber" style={{ marginLeft: 8 }}>SANDBOX</span>
      </div>
      <div className="nav-links">
        {links.map(l => (
          <button key={l.id} className={`nav-link ${page === l.id ? 'active' : ''}`} onClick={() => onNav(l.id)}>{l.label}</button>
        ))}
        {isAdmin && (
          <button className={`nav-link ${page === 'admin' ? 'active' : ''}`} onClick={() => onNav('admin')} style={{ color: 'oklch(0.85 0.14 75)' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <Icon name="lock" size={12}/> Admin CMS
            </span>
          </button>
        )}
      </div>
      <div style={{ flex: 1 }}/>
      <div className="tier-pill">
        <Icon name="bolt" size={12}/> {user.tier.toUpperCase()} TRIAL · 13d
      </div>
      <button className="icon-btn" title="Notifikácie">
        <Icon name="bell" size={18}/>
        {notifCount > 0 && <span className="badge-dot"/>}
      </button>
      <button className="icon-btn" onClick={onLogout} title="Odhlásiť">
        <Icon name="settings" size={18}/>
      </button>
      <div className="avatar" title={user.handle}>{user.handle.slice(0,2).toUpperCase()}</div>
    </nav>
  );
}

// ============ LOGIN ============
function LoginScreen({ onLogin }) {
  const [email, setEmail] = useState('demo@hermes.app');
  const [password, setPassword] = useState('demo');
  const [loading, setLoading] = useState(false);
  const submit = (e) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => onLogin({ email, isAdmin: email.includes('admin') }), 600);
  };
  return (
    <div className="login-shell">
      <div className="login-aurora"/>
      <div className="login-card fade-up">
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 24 }}>
          <div className="brand">
            <div className="brand-mark" style={{ width: 38, height: 38, fontSize: 18, borderRadius: 11 }}>H</div>
            <span style={{ fontSize: 22 }}>HERMES</span>
          </div>
        </div>
        <h1 style={{ fontSize: 32, fontWeight: 600, textAlign: 'center', marginBottom: 8 }}>Prihlásiť sa</h1>
        <p style={{ textAlign: 'center', color: 'var(--text-3)', marginBottom: 28, fontSize: 14 }}>
          AI trading agenti — sandbox bez rizika
        </p>
        <form onSubmit={submit} className="col gap-3">
          <div className="input-wrap">
            <Icon name="mail" size={16}/>
            <input className="input" placeholder="E-mail" value={email} onChange={e => setEmail(e.target.value)}/>
          </div>
          <div className="input-wrap">
            <Icon name="lock" size={16}/>
            <input type="password" className="input" placeholder="Heslo" value={password} onChange={e => setPassword(e.target.value)}/>
          </div>
          <button type="submit" className="btn btn-primary" style={{ padding: '14px', marginTop: 8, fontSize: 15 }} disabled={loading}>
            {loading ? 'Prihlasovanie…' : 'Prihlásiť sa'}
          </button>
          <div className="row between mt-2" style={{ fontSize: 13 }}>
            <a className="text-3" href="#">Zabudnuté heslo?</a>
            <span className="text-3">Nemáte účet? <a href="#" style={{ color: 'oklch(0.85 0.12 295)', textDecoration: 'underline' }}>Registrujte sa</a></span>
          </div>
          <div className="divider"/>
          <button type="button" className="btn btn-secondary" style={{ padding: 12 }}>
            <svg width="16" height="16" viewBox="0 0 24 24"><Icon name="google" size={16}/></svg>
            Prihlásiť cez Google
          </button>
          <div style={{ marginTop: 16, padding: 12, borderRadius: 10, background: 'var(--surface-1)', border: '1px solid var(--border-1)', fontSize: 12, color: 'var(--text-3)' }}>
            <div className="row gap-2" style={{ marginBottom: 6 }}><Icon name="bolt" size={12}/> <strong>Demo prístup:</strong></div>
            <div>User: <span className="mono">demo@hermes.app</span></div>
            <div>Admin: <span className="mono">admin@hermes.app</span></div>
          </div>
        </form>
      </div>
      <div style={{ position: 'absolute', bottom: 20, color: 'var(--text-4)', fontSize: 12 }}>© 2026 Hermes Trading Agents</div>
    </div>
  );
}

window.Hermes = { Icon, Sparkline, AnimatedNumber, MoneyTick, TopNav, LoginScreen,
  DEMO_AGENTS, MARKETPLACE_AGENTS, LEADERBOARD, ADMIN_USERS, TRADES, SYMBOLS, STRATEGIES,
  fmtMoney, fmtPct };


// Hermes screens — dashboard, marketplace, builder, leaderboard, backtest, admin
const { useState, useEffect, useRef, useMemo } = React;
const { Icon, Sparkline, AnimatedNumber, MoneyTick,
  DEMO_AGENTS, MARKETPLACE_AGENTS, LEADERBOARD, ADMIN_USERS, TRADES, SYMBOLS, STRATEGIES,
  fmtMoney, fmtPct } = window.Hermes;

// =================== DASHBOARD ===================
function Dashboard({ user, onNav, agents, setAgents, onToast }) {
  const [totalPnl, setTotalPnl] = useState(367);
  const [tick, setTick] = useState(0);
  // Live tick simulation
  useEffect(() => {
    const id = setInterval(() => {
      setTick(t => t + 1);
      setAgents(prev => prev.map(a => a.status === 'live'
        ? { ...a, pnl: Math.round(a.pnl + (Math.random() - 0.45) * 4) }
        : a));
    }, 3500);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    setTotalPnl(agents.filter(a => a.status === 'live').reduce((s, a) => s + a.pnl, 0));
  }, [agents]);

  const crypto = agents.filter(a => a.category === 'crypto');
  const stocks = agents.filter(a => a.category === 'stocks');
  const tierLimits = { basic: 3, pro: 10, elite: 999 };
  const usedSlots = agents.length;
  const totalSlots = tierLimits[user.tier];

  const togglePause = (id) => {
    setAgents(prev => prev.map(a => a.id === id ? { ...a, status: a.status === 'live' ? 'paused' : 'live' } : a));
    onToast('Stav agenta zmenený');
  };

  return (
    <div className="page fade-up">
      {/* Slot summary cards */}
      <div className="grid-3 mb-4">
        <SlotSummaryCard icon="bot" label="Crypto sloty" used={crypto.length} total={4} color="violet"/>
        <SlotSummaryCard icon="chart" label="Akcie sloty" used={stocks.length} total={4} color="teal"/>
        <SlotSummaryCard icon="trophy" label="Komodity sloty" used={0} total={2} color="amber"/>
      </div>

      {/* Main grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 20 }}>
        {/* LEFT: agent grids */}
        <div className="col gap-6">
          <AgentSection title="CRYPTO" dotColor="violet" agents={crypto} maxSlots={4}
            onAdd={() => onNav('builder')} onToggle={togglePause} onCardClick={(a) => onToast(`Otvorené: ${a.name}`)}/>
          <AgentSection title="AKCIE" dotColor="teal" agents={stocks} maxSlots={4}
            onAdd={() => onNav('builder')} onToggle={togglePause} addLabel="pridať akcie"/>
          <AgentSection title="KOMODITY" dotColor="amber" agents={[]} maxSlots={2}
            onAdd={() => onNav('builder')} addLabel="pridať komoditu"/>
        </div>

        {/* RIGHT: stats panel */}
        <div className="col gap-3">
          <div className="glass p-5">
            <div className="text-2 fs-13 mb-2">Celkové paper P&L</div>
            <div className="row gap-3">
              <MoneyTick value={totalPnl} big/>
            </div>
            <div className="text-3 fs-13 mt-2">{agents.filter(a=>a.status==='live').length} aktívni agenti · {agents.length} celkom</div>
            <div style={{ marginTop: 16 }}>
              <Sparkline data={[100,140,120,180,160,220,200,260,280,320,300,367]} width={300} height={50} animate={true}/>
            </div>
          </div>

          <div className="glass p-4">
            {agents.map((a, i) => (
              <div key={a.id} className="row between" style={{ padding: '10px 0', borderBottom: i < agents.length - 1 ? '1px solid var(--border-1)' : 'none' }}>
                <div className="row gap-2 fs-13">
                  <span className={`dot dot-${a.status === 'live' ? 'live' : 'paused'}`}/>
                  {a.name}
                </div>
                <span className={`mono fs-13 ${a.pnl >= 0 ? 'num-up' : 'num-down'}`}>{fmtMoney(a.pnl)}</span>
              </div>
            ))}
          </div>

          <div className="glass p-4">
            <div className="row between mb-3">
              <div className="fs-13 fw-600" style={{ letterSpacing: '0.06em' }}>{user.tier.toUpperCase()} TIER</div>
              <button className="pill pill-violet" onClick={() => onToast('Upgrade modal')}>Upgrade</button>
            </div>
            <TierStat label="Celkom slotov" value={totalSlots === 999 ? '∞' : totalSlots}/>
            <TierStat label="Použité" value={`${usedSlots} / ${totalSlots === 999 ? '∞' : totalSlots}`}/>
            <TierStat label="Symboly" value="všetky 99"/>
            <TierStat label="Live trading" value="aktívne" valColor="oklch(0.85 0.14 155)"/>
            <TierStat label="History" value="365 dní"/>
            <TierStat label="API" value="Elite only" valColor="var(--text-3)"/>
          </div>

          <div className="glass p-4">
            <div className="fs-13 fw-600 mb-3" style={{ letterSpacing: '0.06em' }}>POSLEDNÉ OBCHODY</div>
            {TRADES.slice(0,4).map((t, i) => (
              <div key={i} className="row between fs-12 mt-2">
                <div className="row gap-2">
                  <span className={`pill ${t.side === 'BUY' ? 'pill-green' : 'pill-red'}`} style={{ padding: '2px 6px', fontSize: 10 }}>{t.side}</span>
                  <span className="text-2">{t.symbol}</span>
                </div>
                <span className="mono text-3">{t.time}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function SlotSummaryCard({ icon, label, used, total, color }) {
  return (
    <div className="glass p-4 shimmer-card">
      <div className="row gap-3">
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: `var(--${color}-soft)`, color: `oklch(0.82 0.14 ${color === 'violet' ? 295 : color === 'teal' ? 185 : 75})`,
          display: 'grid', placeItems: 'center'
        }}><Icon name={icon} size={18}/></div>
        <div>
          <div className="text-2 fs-13">{label}</div>
          <div className="row gap-2 mt-1">
            <span className="mono fw-600 fs-15">{used}/{total}</span>
            <div className="slot-row">
              {Array.from({ length: total }).map((_, i) => (
                <span key={i} className={`slot-sq ${i < used ? `filled-${color}` : ''}`}/>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AgentSection({ title, dotColor, agents, maxSlots, onAdd, onToggle, onCardClick, addLabel = 'pridať crypto' }) {
  const empties = Math.max(0, maxSlots - agents.length);
  return (
    <section>
      <div className="row between mb-3">
        <div className="section-h">
          <span className={`dot dot-${dotColor}`}/> {title}
        </div>
        <div className="row gap-3 fs-13 text-3">
          <span>{agents.filter(a => a.status === 'live').length} aktívne</span>
          <button className="pill pill-violet" onClick={onAdd} style={{ cursor: 'pointer' }}>+ pridať ↗</button>
        </div>
      </div>
      <div className="grid-2">
        {agents.map(a => (
          <div key={a.id} className="slot-card shimmer-card" onClick={() => onCardClick && onCardClick(a)}>
            <div className="row between mb-2">
              <div>
                <div className="fw-600 fs-15">{a.symbol}</div>
                <div className="text-3 fs-12">{a.name}</div>
              </div>
              <div className="row gap-2">
                {a.status === 'live' ? <div className="live-ring"/> : <span className="dot dot-paused"/>}
              </div>
            </div>
            <div className="row between">
              <div className="row gap-3 fs-12">
                <span className="text-3">Win <span className="num-up mono">{a.win}%</span></span>
                <span className="text-3">P&L <span className={`mono ${a.pnl >= 0 ? 'num-up' : 'num-down'}`}>{fmtMoney(a.pnl)}</span></span>
                <span className="pill pill-gray" style={{ padding: '2px 6px', fontSize: 9 }}>paper</span>
              </div>
              <Sparkline data={a.sparks} width={50} height={18} color={a.pnl >= 0 ? 'oklch(0.78 0.16 155)' : 'oklch(0.70 0.20 25)'}/>
            </div>
            <div className="row gap-2 mt-3" onClick={e => e.stopPropagation()}>
              <button className="pill pill-gray" style={{ padding: '4px 8px', fontSize: 10 }} onClick={() => onToggle(a.id)}>
                <Icon name={a.status === 'live' ? 'pause' : 'play'} size={10}/>
                {a.status === 'live' ? 'pauza' : 'spusti'}
              </button>
              <button className="pill pill-gray" style={{ padding: '4px 8px', fontSize: 10 }}><Icon name="chart" size={10}/> graf</button>
              <button className="pill pill-gray" style={{ padding: '4px 8px', fontSize: 10 }}><Icon name="share" size={10}/> share</button>
            </div>
          </div>
        ))}
        {Array.from({ length: empties }).map((_, i) => (
          <div key={i} className="slot-card empty" onClick={onAdd}>
            <div className="row gap-2"><Icon name="plus" size={14}/> {addLabel}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function TierStat({ label, value, valColor }) {
  return (
    <div className="row between fs-13" style={{ padding: '7px 0' }}>
      <span className="text-3">{label}</span>
      <span className="mono fw-500" style={{ color: valColor || 'var(--text-1)' }}>{value}</span>
    </div>
  );
}

// =================== MARKETPLACE ===================
function Marketplace({ onNav, onSubscribe, onToast }) {
  const [tab, setTab] = useState('system');
  const [filter, setFilter] = useState('all');
  const [q, setQ] = useState('');
  const filtered = MARKETPLACE_AGENTS.filter(a => 
    (filter === 'all' || a.symbol.toLowerCase().includes(filter)) &&
    (q === '' || a.name.toLowerCase().includes(q.toLowerCase()))
  );
  return (
    <div className="page fade-up">
      <div className="row between mb-4">
        <div>
          <h1 className="fs-28 fw-600">Marketplace</h1>
          <p className="text-3 fs-13 mt-1">Predplaťte si overených AI agentov alebo objavujte stratégie od komunity</p>
        </div>
        <div className="row gap-2">
          <button className="btn btn-secondary" onClick={() => onNav('builder')}>
            <Icon name="plus" size={14}/> Vytvoriť vlastného
          </button>
        </div>
      </div>

      <div className="tabs mb-4">
        <button className={`tab ${tab==='system'?'active':''}`} onClick={()=>setTab('system')}>System agenti · 50</button>
        <button className={`tab ${tab==='community'?'active':''}`} onClick={()=>setTab('community')}>Community · 248</button>
        <button className={`tab ${tab==='subscribed'?'active':''}`} onClick={()=>setTab('subscribed')}>Moje predplatné · 2</button>
      </div>

      <div className="row gap-3 mb-4">
        <div className="input-wrap" style={{ flex: 1, maxWidth: 360 }}>
          <Icon name="search" size={16}/>
          <input className="input" placeholder="Hľadať agenta, symbol, autora…" value={q} onChange={e=>setQ(e.target.value)}/>
        </div>
        {['all','btc','eth','sol','nvda'].map(f => (
          <button key={f} className={`pill ${filter===f?'pill-violet':'pill-gray'}`} style={{ padding: '6px 12px', cursor: 'pointer' }} onClick={() => setFilter(f)}>{f.toUpperCase()}</button>
        ))}
      </div>

      <div className="grid-3">
        {filtered.map(a => (
          <div key={a.id} className="glass p-5 shimmer-card" style={{ position: 'relative' }}>
            {a.badge && (
              <span className={`pill ${a.badge==='top_gainer'?'pill-amber':a.badge==='hot_streak'?'pill-red':a.badge==='steady'?'pill-teal':'pill-violet'}`}
                    style={{ position: 'absolute', top: 16, right: 16 }}>
                {a.badge==='top_gainer'?'🏆 Top':a.badge==='hot_streak'?'🔥 Hot':a.badge==='steady'?'Steady':'Reliable'}
              </span>
            )}
            <div className="row gap-3 mb-3">
              <div style={{ width: 40, height: 40, borderRadius: 10, background: 'var(--violet-soft)', color: 'oklch(0.85 0.12 295)', display: 'grid', placeItems: 'center' }}>
                <Icon name="bot" size={20}/>
              </div>
              <div>
                <div className="fw-600 fs-15">{a.name}</div>
                <div className="text-3 fs-12">{a.symbol} · {a.strategy}</div>
              </div>
            </div>
            <div className="row gap-3 mb-3 fs-12">
              <span className="text-3">by</span>
              <span className="row gap-1">
                <span>{a.author}</span>
                {a.verified && <span style={{ color: 'oklch(0.82 0.13 185)' }}>✓</span>}
              </span>
            </div>
            <div className="grid-2 mb-3" style={{ gap: 8 }}>
              <div className="glass-light p-3">
                <div className="text-3 fs-12">Win rate</div>
                <div className="mono num-up fw-600 fs-15">{a.win}%</div>
              </div>
              <div className="glass-light p-3">
                <div className="text-3 fs-12">30d P&L</div>
                <div className={`mono fw-600 fs-15 ${a.monthlyPnl>=0?'num-up':'num-down'}`}>{fmtPct(a.monthlyPnl)}</div>
              </div>
            </div>
            <div className="row between">
              <span className="text-3 fs-12"><Icon name="users" size={11}/> {a.subs.toLocaleString()} sledovateľov</span>
              <button className="btn btn-primary" style={{ padding: '6px 14px', fontSize: 12 }} onClick={() => { onSubscribe(a); onToast(`Predplatené: ${a.name}`); }}>Predplatiť</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// =================== AGENT BUILDER ===================
function AgentBuilder({ onNav, onCreate, onToast }) {
  const [step, setStep] = useState(1);
  const [data, setData] = useState({ category: 'crypto', symbol: 'BTC/USD', strategy: 'momentum', risk: 'medium', maxPos: 200, name: '' });
  const total = 4;
  const next = () => setStep(s => Math.min(total, s + 1));
  const back = () => setStep(s => Math.max(1, s - 1));
  const finish = () => {
    onCreate({ ...data, name: data.name || `${data.symbol} ${STRATEGIES.find(s=>s.id===data.strategy).label}` });
    onToast('✓ Agent vytvorený a spustený v paper móde');
    onNav('dashboard');
  };

  return (
    <div className="page fade-up" style={{ maxWidth: 880 }}>
      <div className="row between mb-4">
        <div>
          <h1 className="fs-28 fw-600">Agent Builder</h1>
          <p className="text-3 fs-13 mt-1">Vytvor si AI agenta za 60 sekúnd — bez kódu</p>
        </div>
        <button className="btn btn-ghost" onClick={() => onNav('dashboard')}><Icon name="x" size={14}/> Zrušiť</button>
      </div>

      {/* Stepper */}
      <div className="glass p-5 mb-4">
        <div className="row between mb-3">
          {['Symbol', 'Stratégia', 'Risk', 'Názov'].map((label, i) => (
            <div key={i} className="row gap-2" style={{ flex: 1, opacity: step >= i+1 ? 1 : 0.5 }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%',
                background: step > i+1 ? 'oklch(0.78 0.16 155)' : step === i+1 ? 'oklch(0.72 0.18 295)' : 'var(--surface-3)',
                display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 600
              }}>
                {step > i+1 ? <Icon name="check" size={14}/> : i+1}
              </div>
              <span className="fs-13 fw-500">{label}</span>
              {i < 3 && <div className="flex-1" style={{ height: 1, background: 'var(--border-1)' }}/>}
            </div>
          ))}
        </div>
        <div className="progress"><div className="progress-fill" style={{ width: `${(step/total)*100}%`, transition: 'width 0.4s' }}/></div>
      </div>

      <div className="glass p-6">
        {step === 1 && (
          <div className="fade-up">
            <h2 className="fs-22 fw-600 mb-2">Vyber asset</h2>
            <p className="text-3 fs-13 mb-4">Aký trh bude agent obchodovať?</p>
            <div className="row gap-2 mb-4">
              {['crypto','stocks','commodities'].map(c => (
                <button key={c} className={`pill ${data.category===c?'pill-violet':'pill-gray'}`}
                  style={{ padding: '8px 14px', cursor: 'pointer' }}
                  onClick={() => setData({ ...data, category: c, symbol: SYMBOLS[c][0] })}>
                  {c.toUpperCase()}
                </button>
              ))}
            </div>
            <div className="grid-4" style={{ gap: 10 }}>
              {SYMBOLS[data.category].map(s => (
                <button key={s} className="slot-card" style={{ padding: 14, textAlign: 'left',
                  borderColor: data.symbol === s ? 'oklch(0.72 0.18 295 / 0.6)' : undefined,
                  background: data.symbol === s ? 'var(--violet-soft)' : undefined
                }} onClick={() => setData({ ...data, symbol: s })}>
                  <div className="fw-600 fs-15">{s.split(' ')[0]}</div>
                  <div className="text-3 fs-12">{data.category === 'crypto' ? 'Crypto' : data.category === 'stocks' ? 'Akcia' : 'Komodita'}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="fade-up">
            <h2 className="fs-22 fw-600 mb-2">Vyber stratégiu</h2>
            <p className="text-3 fs-13 mb-4">Ako sa má agent rozhodovať?</p>
            <div className="col gap-2">
              {STRATEGIES.map(s => (
                <button key={s.id} className="slot-card" style={{ textAlign: 'left',
                  borderColor: data.strategy === s.id ? 'oklch(0.72 0.18 295 / 0.6)' : undefined,
                  background: data.strategy === s.id ? 'var(--violet-soft)' : undefined
                }} onClick={() => setData({ ...data, strategy: s.id })}>
                  <div className="row between">
                    <div className="fw-600 fs-15">{s.label}</div>
                    {data.strategy === s.id && <Icon name="check" size={16} style={{ color: 'oklch(0.85 0.12 295)' }}/>}
                  </div>
                  <div className="text-3 fs-13 mt-1">{s.desc}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="fade-up">
            <h2 className="fs-22 fw-600 mb-2">Risk profil</h2>
            <p className="text-3 fs-13 mb-4">Koľko môže agent riskovať na jeden obchod?</p>
            <div className="grid-3 mb-4">
              {[
                { id: 'low', label: 'Nízky', desc: '1-2% per trade', color: 'teal' },
                { id: 'medium', label: 'Stredný', desc: '3-5% per trade', color: 'violet' },
                { id: 'high', label: 'Vysoký', desc: '6-10% per trade', color: 'amber' },
              ].map(r => (
                <button key={r.id} className="slot-card" style={{ textAlign: 'left',
                  borderColor: data.risk === r.id ? `oklch(0.72 0.18 ${r.color === 'teal'?185:r.color==='amber'?75:295} / 0.6)` : undefined,
                  background: data.risk === r.id ? `var(--${r.color}-soft)` : undefined
                }} onClick={() => setData({ ...data, risk: r.id })}>
                  <div className="fw-600 fs-15">{r.label}</div>
                  <div className="text-3 fs-12 mt-1">{r.desc}</div>
                </button>
              ))}
            </div>
            <div className="glass-light p-4">
              <div className="row between mb-2">
                <span className="fs-13 text-2">Max veľkosť pozície</span>
                <span className="mono fw-600">${data.maxPos}</span>
              </div>
              <input type="range" min="50" max="1000" step="50" value={data.maxPos}
                onChange={e => setData({ ...data, maxPos: +e.target.value })} style={{ width: '100%' }}/>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="fade-up">
            <h2 className="fs-22 fw-600 mb-2">Pomenuj svojho agenta</h2>
            <p className="text-3 fs-13 mb-4">Pod akým menom ho uvidíš v dashboarde a leaderboarde?</p>
            <input className="input" style={{ paddingLeft: 14 }} placeholder={`${data.symbol} ${STRATEGIES.find(s=>s.id===data.strategy).label}`}
              value={data.name} onChange={e => setData({ ...data, name: e.target.value })}/>

            <div className="glass-light p-4 mt-4">
              <div className="fs-12 fw-600 text-2 mb-3" style={{ letterSpacing: '0.06em' }}>AI SUMMARY</div>
              <div className="fs-14" style={{ lineHeight: 1.7 }}>
                Tento agent bude obchodovať <strong>{data.symbol}</strong> pomocou stratégie <strong>{STRATEGIES.find(s=>s.id===data.strategy).label}</strong>.
                {' '}Pri risk profile <strong>{data.risk === 'low' ? 'Nízky' : data.risk === 'medium' ? 'Stredný' : 'Vysoký'}</strong> bude
                {' '}otvárať pozície max <strong className="mono">${data.maxPos}</strong>. Spustí sa v paper móde — žiadne reálne peniaze.
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="row between mt-4">
        <button className="btn btn-secondary" onClick={back} disabled={step === 1} style={{ opacity: step === 1 ? 0.4 : 1 }}>Späť</button>
        {step < total ? (
          <button className="btn btn-primary" onClick={next}>Pokračovať <Icon name="chevron" size={14}/></button>
        ) : (
          <button className="btn btn-primary" onClick={finish}><Icon name="bolt" size={14}/> Spustiť agenta</button>
        )}
      </div>
    </div>
  );
}

window.HermesScreens = { Dashboard, Marketplace, AgentBuilder };


// Hermes — leaderboard, backtest, admin
const { useState, useEffect, useRef, useMemo } = React;
const { Icon, Sparkline, AnimatedNumber, MoneyTick,
  DEMO_AGENTS, MARKETPLACE_AGENTS, LEADERBOARD, ADMIN_USERS, TRADES, SYMBOLS, STRATEGIES,
  fmtMoney, fmtPct } = window.Hermes;

// =================== LEADERBOARD ===================
function Leaderboard({ user, onToast }) {
  const [period, setPeriod] = useState('weekly');
  return (
    <div className="page fade-up">
      <div className="row between mb-4">
        <div>
          <h1 className="fs-28 fw-600">Leaderboard</h1>
          <p className="text-3 fs-13 mt-1">Najlepšie výsledky tohto týždňa · cache 6h</p>
        </div>
        <div className="row gap-2">
          {[['weekly','Týždenný'],['monthly','Mesačný'],['alltime','All-time']].map(([id,l]) => (
            <button key={id} className={`pill ${period===id?'pill-violet':'pill-gray'}`}
              style={{ padding: '6px 14px', cursor: 'pointer' }} onClick={()=>setPeriod(id)}>{l}</button>
          ))}
        </div>
      </div>

      {/* Podium top 3 */}
      <div className="grid-3 mb-6">
        {LEADERBOARD.slice(0,3).map((u, i) => (
          <div key={u.user} className={`glass p-5 ${i===0?'glow-violet':''}`}
            style={{ textAlign: 'center', position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', top: 12, right: 12, fontSize: 28 }}>{i===0?'🏆':i===1?'🥈':'🥉'}</div>
            <div className="avatar" style={{ width: 56, height: 56, fontSize: 18, margin: '0 auto 12px',
              background: i===0 ? 'linear-gradient(135deg, oklch(0.78 0.16 75), oklch(0.68 0.18 50))' :
                          i===1 ? 'linear-gradient(135deg, oklch(0.78 0.06 240), oklch(0.65 0.04 240))' :
                                  'linear-gradient(135deg, oklch(0.65 0.13 30), oklch(0.55 0.10 30))'
            }}>{u.user.slice(0,2).toUpperCase()}</div>
            <div className="fs-15 fw-600">{u.user}</div>
            <div className={`pill pill-${u.tier==='elite'?'amber':'violet'} mt-2`} style={{ display: 'inline-flex' }}>{u.tier.toUpperCase()}</div>
            <div className="mt-3">
              <div className="text-3 fs-12">Týždňový P&L</div>
              <div className="mono fs-28 fw-700 num-up">{fmtMoney(u.pnl)}</div>
            </div>
            <div className="row center gap-4 mt-3 fs-12 text-3">
              <span>Win <span className="mono num-up">{u.win}%</span></span>
              <span>{u.trades} trades</span>
              <span>{u.agents} agentov</span>
            </div>
          </div>
        ))}
      </div>

      {/* Full table */}
      <div className="glass" style={{ overflow: 'hidden' }}>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 60 }}>#</th>
              <th>User</th>
              <th>Tier</th>
              <th>Týž. P&L</th>
              <th>Win rate</th>
              <th>Trades</th>
              <th>Agenti</th>
              <th>Δ</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {LEADERBOARD.map(u => (
              <tr key={u.user} style={u.isMe ? { background: 'oklch(0.72 0.18 295 / 0.08)' } : {}}>
                <td className="mono fw-600 fs-15">{u.rank}</td>
                <td>
                  <div className="row gap-2">
                    <div className="avatar" style={{ width: 28, height: 28, fontSize: 11 }}>{u.user.slice(0,2).toUpperCase()}</div>
                    <span className="fw-500">{u.user}</span>
                    {u.isMe && <span className="pill pill-violet" style={{ padding: '2px 8px' }}>Ty</span>}
                  </div>
                </td>
                <td><span className={`pill pill-${u.tier==='elite'?'amber':u.tier==='pro'?'violet':'gray'}`}>{u.tier.toUpperCase()}</span></td>
                <td className={`mono fw-600 ${u.pnl>=0?'num-up':'num-down'}`}>{fmtMoney(u.pnl)}</td>
                <td className="mono">{u.win}%</td>
                <td className="mono text-2">{u.trades}</td>
                <td className="mono text-2">{u.agents}</td>
                <td>
                  {u.change > 0 && <span className="num-up mono row gap-1"><Icon name="arrowUp" size={10}/>{u.change}</span>}
                  {u.change < 0 && <span className="num-down mono row gap-1"><Icon name="arrowDown" size={10}/>{Math.abs(u.change)}</span>}
                  {u.change === 0 && <span className="text-3 mono">—</span>}
                </td>
                <td>
                  <button className="btn-ghost" style={{ padding: 6 }} onClick={() => onToast(`Profil ${u.user}`)}>
                    <Icon name="chevron" size={14}/>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// =================== BACKTEST ===================
function Backtest({ user, onToast }) {
  const [symbol, setSymbol] = useState('BTC/USD');
  const [strategy, setStrategy] = useState('momentum');
  const [period, setPeriod] = useState('30d');
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState(null);
  const tierLocked = period === '1y' && user.tier !== 'elite';

  const runBacktest = () => {
    if (tierLocked) return onToast('1y backtest je len pre Elite tier');
    setRunning(true);
    setTimeout(() => {
      setResults({
        winRate: 65 + Math.floor(Math.random() * 12),
        sharpe: (1.2 + Math.random() * 0.8).toFixed(2),
        maxDD: -(8 + Math.floor(Math.random() * 12)),
        trades: 124 + Math.floor(Math.random() * 80),
        finalPnl: 8.4 + Math.random() * 22,
      });
      setRunning(false);
      onToast('✓ Backtest dokončený');
    }, 1400);
  };

  return (
    <div className="page fade-up">
      <div className="row between mb-4">
        <div>
          <h1 className="fs-28 fw-600">Backtesting</h1>
          <p className="text-3 fs-13 mt-1">Otestuj stratégiu na Binance historických dátach</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 20 }}>
        <div className="glass p-5 col gap-4">
          <div>
            <div className="fs-12 fw-600 text-2 mb-2" style={{ letterSpacing: '0.06em' }}>SYMBOL</div>
            <select className="input" style={{ paddingLeft: 14 }} value={symbol} onChange={e=>setSymbol(e.target.value)}>
              {[...SYMBOLS.crypto, ...SYMBOLS.stocks].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <div className="fs-12 fw-600 text-2 mb-2" style={{ letterSpacing: '0.06em' }}>STRATÉGIA</div>
            <select className="input" style={{ paddingLeft: 14 }} value={strategy} onChange={e=>setStrategy(e.target.value)}>
              {STRATEGIES.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <div className="fs-12 fw-600 text-2 mb-2" style={{ letterSpacing: '0.06em' }}>OBDOBIE</div>
            <div className="col gap-2">
              {[
                {id:'7d', l:'7 dní', t:'basic'},
                {id:'30d', l:'30 dní', t:'basic'},
                {id:'90d', l:'90 dní', t:'pro'},
                {id:'1y', l:'1 rok', t:'elite'},
              ].map(p => {
                const locked = (p.t === 'elite' && user.tier !== 'elite') || (p.t === 'pro' && user.tier === 'basic');
                return (
                  <button key={p.id} className="slot-card" style={{ padding: 12, textAlign: 'left',
                    borderColor: period === p.id ? 'oklch(0.72 0.18 295 / 0.6)' : undefined,
                    background: period === p.id ? 'var(--violet-soft)' : undefined,
                    opacity: locked ? 0.5 : 1
                  }} onClick={() => !locked && setPeriod(p.id)} disabled={locked}>
                    <div className="row between">
                      <span className="fs-13 fw-500">{p.l}</span>
                      {locked ? <Icon name="lock" size={12}/> : period === p.id && <Icon name="check" size={12}/>}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
          <button className="btn btn-primary" onClick={runBacktest} disabled={running} style={{ marginTop: 'auto' }}>
            {running ? <><span className="live-pulse">⚙</span> Spúšťa…</> : <><Icon name="play" size={14}/> Spustiť backtest</>}
          </button>
        </div>

        <div className="col gap-3">
          {!results && !running && (
            <div className="glass p-6" style={{ minHeight: 400, display: 'grid', placeItems: 'center', textAlign: 'center' }}>
              <div>
                <Icon name="chart" size={48} style={{ color: 'var(--text-4)', marginBottom: 12 }}/>
                <div className="fs-15 text-2">Vyber parametre a spusti backtest</div>
                <div className="text-3 fs-13 mt-2">Equity curve, win rate, Sharpe ratio, max drawdown</div>
              </div>
            </div>
          )}
          {running && (
            <div className="glass p-6" style={{ minHeight: 400, display: 'grid', placeItems: 'center' }}>
              <div className="col center gap-3">
                <div style={{ fontSize: 32 }}>⚙</div>
                <div className="fs-15 fw-500">Načítavajú sa Binance dáta…</div>
                <div className="text-3 fs-13">Spracovávam {symbol} · {period}</div>
                <div className="progress" style={{ width: 240, marginTop: 8 }}><div className="progress-fill" style={{ width: '70%' }}/></div>
              </div>
            </div>
          )}
          {results && (
            <>
              <div className="grid-4">
                <MetricCard label="Win rate" value={`${results.winRate}%`} delta="+2.3%" color="green"/>
                <MetricCard label="Sharpe ratio" value={results.sharpe} delta="excellent" color="violet"/>
                <MetricCard label="Max drawdown" value={`${results.maxDD}%`} delta="acceptable" color="amber"/>
                <MetricCard label="Trades" value={results.trades} delta={`${period}`} color="teal"/>
              </div>
              <div className="glass p-5">
                <div className="row between mb-3">
                  <div>
                    <div className="fs-13 text-2">Equity curve · {symbol}</div>
                    <div className="mono fs-22 fw-700 num-up mt-1">{fmtPct(results.finalPnl)}</div>
                  </div>
                  <div className="row gap-2">
                    <button className="pill pill-gray" style={{ padding: '6px 12px' }}><Icon name="copy" size={11}/> CSV</button>
                    <button className="pill pill-gray" style={{ padding: '6px 12px' }}><Icon name="share" size={11}/> SVG</button>
                  </div>
                </div>
                <EquityCurve seed={results.finalPnl}/>
              </div>
              <div className="glass p-5">
                <div className="fs-13 fw-600 mb-3" style={{ letterSpacing: '0.06em' }}>VZORKA OBCHODOV</div>
                <table className="tbl">
                  <thead>
                    <tr><th>Čas</th><th>Side</th><th>Cena</th><th>Veľk.</th><th>P&L</th></tr>
                  </thead>
                  <tbody>
                    {TRADES.map((t, i) => (
                      <tr key={i}>
                        <td className="mono text-3">{t.time}</td>
                        <td><span className={`pill ${t.side==='BUY'?'pill-green':'pill-red'}`} style={{ padding: '2px 8px' }}>{t.side}</span></td>
                        <td className="mono">{t.price.toLocaleString()}</td>
                        <td className="mono">{t.qty}</td>
                        <td className={`mono ${t.pnl>0?'num-up':t.pnl<0?'num-down':'text-3'}`}>{t.pnl===null?'—':fmtMoney(t.pnl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, delta, color }) {
  return (
    <div className="glass p-4 shimmer-card">
      <div className="text-3 fs-12">{label}</div>
      <div className="mono fs-22 fw-700 mt-1">{value}</div>
      <div className={`pill pill-${color} mt-2`} style={{ padding: '2px 8px' }}>{delta}</div>
    </div>
  );
}

function EquityCurve({ seed = 18 }) {
  const points = useMemo(() => {
    const arr = [100];
    for (let i = 0; i < 60; i++) {
      const noise = (Math.sin(i * 0.4 + seed) * 2) + (Math.random() - 0.4) * 3;
      arr.push(Math.max(80, arr[arr.length - 1] + noise));
    }
    arr[arr.length - 1] = 100 + seed;
    return arr;
  }, [seed]);
  const W = 800, H = 220;
  const min = Math.min(...points), max = Math.max(...points);
  const xy = (v, i) => [(i / (points.length - 1)) * W, H - ((v - min) / (max - min)) * (H - 20) - 10];
  const path = points.map((v, i) => { const [x, y] = xy(v, i); return (i === 0 ? 'M' : 'L') + x + ',' + y; }).join(' ');
  const area = path + ` L${W},${H} L0,${H} Z`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 220 }}>
      <defs>
        <linearGradient id="eq-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="oklch(0.72 0.18 295)" stopOpacity="0.4"/>
          <stop offset="100%" stopColor="oklch(0.72 0.18 295)" stopOpacity="0"/>
        </linearGradient>
      </defs>
      {[0,1,2,3].map(i => <line key={i} x1="0" x2={W} y1={(H/4)*i+10} y2={(H/4)*i+10} stroke="var(--border-1)" strokeDasharray="2 4"/>)}
      <path d={area} fill="url(#eq-grad)"/>
      <path className="spark-path" d={path} fill="none" stroke="oklch(0.72 0.18 295)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

// =================== ADMIN CMS ===================
function AdminCMS({ onToast, onNav }) {
  const [section, setSection] = useState('users');
  const [users, setUsers] = useState(ADMIN_USERS);
  const [q, setQ] = useState('');
  const [tierFilter, setTierFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selected, setSelected] = useState(null);
  const [confirmAction, setConfirmAction] = useState(null);

  const filtered = users.filter(u =>
    (q === '' || u.email.includes(q.toLowerCase()) || u.handle.includes(q.toLowerCase())) &&
    (tierFilter === 'all' || u.tier === tierFilter) &&
    (statusFilter === 'all' || u.status === statusFilter)
  );

  const stats = {
    total: users.length,
    active: users.filter(u => u.status === 'active').length,
    suspended: users.filter(u => u.status === 'suspended').length,
    banned: users.filter(u => u.status === 'banned').length,
    elite: users.filter(u => u.tier === 'elite').length,
    pro: users.filter(u => u.tier === 'pro').length,
    basic: users.filter(u => u.tier === 'basic').length,
    revenue: users.filter(u => u.tier !== 'basic').reduce((s, u) => s + (u.tier === 'elite' ? 49 : 19), 0),
  };

  const updateUser = (id, patch) => {
    setUsers(prev => prev.map(u => u.id === id ? { ...u, ...patch } : u));
    setSelected(prev => prev && prev.id === id ? { ...prev, ...patch } : prev);
  };

  const performAction = () => {
    if (!confirmAction) return;
    const { id, action } = confirmAction;
    if (action === 'suspend') updateUser(id, { status: 'suspended', suspendReason: 'Admin akcia' });
    if (action === 'ban') updateUser(id, { status: 'banned', suspendReason: 'Admin akcia — permanent' });
    if (action === 'reactivate') updateUser(id, { status: 'active', suspendReason: undefined });
    if (action === 'delete') { setUsers(prev => prev.filter(u => u.id !== id)); setSelected(null); }
    if (action === 'verify') updateUser(id, { verified: true });
    onToast(`✓ ${action === 'suspend' ? 'Pozastavené' : action === 'ban' ? 'Zabanovaný' : action === 'reactivate' ? 'Reaktivovaný' : action === 'delete' ? 'Vymazaný' : 'Verifikovaný'}`);
    setConfirmAction(null);
  };

  const setTier = (id, tier) => { updateUser(id, { tier }); onToast(`Tier zmenený na ${tier.toUpperCase()}`); };

  return (
    <div className="page fade-up" style={{ maxWidth: 1500 }}>
      <div className="row between mb-4">
        <div>
          <div className="row gap-2">
            <h1 className="fs-28 fw-600">Admin CMS</h1>
            <span className="pill pill-amber"><Icon name="lock" size={10}/> Admin only</span>
          </div>
          <p className="text-3 fs-13 mt-1">Správa userov, marketplace, demo agentov a systémových štatistík</p>
        </div>
        <div className="row gap-2">
          <button className="btn btn-secondary" onClick={() => onToast('Audit log otvorený')}><Icon name="flag" size={14}/> Audit log</button>
          <button className="btn btn-secondary" onClick={() => onToast('Export CSV')}><Icon name="copy" size={14}/> Export</button>
        </div>
      </div>

      {/* Top stats */}
      <div className="grid-4 mb-4">
        <AdminStat label="Celkom userov" value={stats.total} delta="+24 / 7d" color="violet"/>
        <AdminStat label="Aktívni" value={stats.active} delta={`${Math.round((stats.active/stats.total)*100)}%`} color="green"/>
        <AdminStat label="Pozastavení" value={stats.suspended + stats.banned} delta={`${stats.banned} banned`} color="red"/>
        <AdminStat label="MRR (mes.)" value={`€${stats.revenue}`} delta={`${stats.elite}E · ${stats.pro}P`} color="amber"/>
      </div>

      {/* Tabs */}
      <div className="tabs mb-4">
        {[
          ['users','Users · ' + users.length],
          ['marketplace','Marketplace approval · 4'],
          ['demo','Demo agenti · 12'],
          ['stats','System stats'],
        ].map(([id, l]) => (
          <button key={id} className={`tab ${section===id?'active':''}`} onClick={()=>setSection(id)}>{l}</button>
        ))}
      </div>

      {section === 'users' && (
        <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 380px' : '1fr', gap: 20 }}>
          <div>
            {/* Filters */}
            <div className="row gap-3 mb-3">
              <div className="input-wrap" style={{ flex: 1, maxWidth: 340 }}>
                <Icon name="search" size={16}/>
                <input className="input" placeholder="Hľadať email, handle…" value={q} onChange={e=>setQ(e.target.value)}/>
              </div>
              <select className="input" style={{ paddingLeft: 14, maxWidth: 140 }} value={tierFilter} onChange={e=>setTierFilter(e.target.value)}>
                <option value="all">Všetky tiery</option>
                <option value="basic">Basic</option>
                <option value="pro">Pro</option>
                <option value="elite">Elite</option>
              </select>
              <select className="input" style={{ paddingLeft: 14, maxWidth: 160 }} value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}>
                <option value="all">Všetky statusy</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
                <option value="banned">Banned</option>
                <option value="pending">Pending</option>
              </select>
            </div>

            <div className="glass" style={{ overflow: 'hidden' }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th><input type="checkbox"/></th>
                    <th>User</th>
                    <th>Tier</th>
                    <th>Status</th>
                    <th>Agenti</th>
                    <th>P&L</th>
                    <th>Joined</th>
                    <th>Last seen</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(u => (
                    <tr key={u.id} onClick={() => setSelected(u)} style={{ cursor: 'pointer',
                      background: selected?.id === u.id ? 'oklch(0.72 0.18 295 / 0.08)' : undefined }}>
                      <td onClick={e => e.stopPropagation()}><input type="checkbox"/></td>
                      <td>
                        <div className="row gap-2">
                          <div className="avatar" style={{ width: 30, height: 30, fontSize: 11 }}>{u.handle.slice(0,2).toUpperCase()}</div>
                          <div>
                            <div className="fw-500 fs-13 row gap-1">{u.handle} {u.verified && <span style={{color:'oklch(0.82 0.13 185)'}}>✓</span>}</div>
                            <div className="text-3 fs-12">{u.email}</div>
                          </div>
                        </div>
                      </td>
                      <td><span className={`pill pill-${u.tier==='elite'?'amber':u.tier==='pro'?'violet':'gray'}`}>{u.tier.toUpperCase()}</span></td>
                      <td><StatusPill status={u.status}/></td>
                      <td className="mono">{u.agents}</td>
                      <td className={`mono ${u.pnl>0?'num-up':u.pnl<0?'num-down':'text-3'}`}>{u.pnl===0?'—':fmtMoney(u.pnl)}</td>
                      <td className="text-3 fs-12 mono">{u.joined}</td>
                      <td className="text-3 fs-12">{u.lastSeen}</td>
                      <td onClick={e=>e.stopPropagation()}>
                        <button className="btn-ghost" style={{ padding: 6 }}><Icon name="chevron" size={14}/></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="row between mt-3 fs-12 text-3">
              <span>{filtered.length} z {users.length} userov</span>
              <div className="row gap-2">
                <button className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: 12 }}>‹</button>
                <span className="mono">1 / 1</span>
                <button className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: 12 }}>›</button>
              </div>
            </div>
          </div>

          {/* Detail panel */}
          {selected && (
            <UserDetail user={selected} onClose={() => setSelected(null)}
              onAction={(action) => setConfirmAction({ id: selected.id, action })}
              onSetTier={(t) => setTier(selected.id, t)}/>
          )}
        </div>
      )}

      {section === 'marketplace' && <MarketplaceApproval onToast={onToast}/>}
      {section === 'demo' && <DemoAgents onToast={onToast}/>}
      {section === 'stats' && <SystemStats stats={stats}/>}

      {/* Confirm modal */}
      {confirmAction && (
        <div className="modal-overlay" onClick={() => setConfirmAction(null)}>
          <div className="modal p-6" onClick={e => e.stopPropagation()}>
            <h2 className="fs-22 fw-600 mb-2">Potvrdiť akciu</h2>
            <p className="text-2 mb-4">
              {confirmAction.action === 'ban' && 'Zabanovať usera permanentne? Tento krok je nezvratný cez UI.'}
              {confirmAction.action === 'suspend' && 'Pozastaviť usera? Stratí prístup, ale dáta zostanú.'}
              {confirmAction.action === 'reactivate' && 'Reaktivovať usera a obnoviť prístup?'}
              {confirmAction.action === 'delete' && 'NATRVALO vymazať user data? Vrátane všetkých agentov a histórie.'}
              {confirmAction.action === 'verify' && 'Potvrdiť verifikáciu usera?'}
            </p>
            <div className="row gap-2">
              <button className="btn btn-secondary flex-1" onClick={() => setConfirmAction(null)}>Zrušiť</button>
              <button className={`btn flex-1 ${confirmAction.action==='ban'||confirmAction.action==='delete'?'btn-danger':'btn-primary'}`}
                onClick={performAction}>Potvrdiť</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function AdminStat({ label, value, delta, color }) {
  return (
    <div className="glass p-4 shimmer-card">
      <div className="text-3 fs-12">{label}</div>
      <div className="mono fs-28 fw-700 mt-1">{value}</div>
      <div className={`pill pill-${color} mt-2`} style={{ padding: '2px 8px' }}>{delta}</div>
    </div>
  );
}

function StatusPill({ status }) {
  const map = {
    active: { c: 'green', l: 'Active' },
    suspended: { c: 'amber', l: 'Suspended' },
    banned: { c: 'red', l: 'Banned' },
    pending: { c: 'gray', l: 'Pending' },
  };
  const m = map[status];
  return <span className={`pill pill-${m.c}`}>{m.l}</span>;
}

function UserDetail({ user, onClose, onAction, onSetTier }) {
  return (
    <div className="glass p-5 fade-up" style={{ position: 'sticky', top: 100, alignSelf: 'flex-start', maxHeight: 'calc(100vh - 120px)', overflow: 'auto' }}>
      <div className="row between mb-4">
        <div className="fs-12 fw-600 text-2" style={{ letterSpacing: '0.06em' }}>USER DETAIL</div>
        <button className="btn-ghost" onClick={onClose} style={{ padding: 4 }}><Icon name="x" size={14}/></button>
      </div>

      <div className="col center mb-4">
        <div className="avatar" style={{ width: 64, height: 64, fontSize: 22, marginBottom: 12 }}>{user.handle.slice(0,2).toUpperCase()}</div>
        <div className="fs-18 fw-600 row gap-1">{user.handle} {user.verified && <span style={{ color: 'oklch(0.82 0.13 185)' }}>✓</span>}</div>
        <div className="text-3 fs-13">{user.email}</div>
        <div className="row gap-2 mt-2">
          <span className={`pill pill-${user.tier==='elite'?'amber':user.tier==='pro'?'violet':'gray'}`}>{user.tier.toUpperCase()}</span>
          <StatusPill status={user.status}/>
        </div>
      </div>

      {user.suspendReason && (
        <div className="glass-light p-3 mb-3" style={{ background: 'oklch(0.70 0.20 25 / 0.10)', border: '1px solid oklch(0.70 0.20 25 / 0.3)' }}>
          <div className="fs-12 fw-600" style={{ color: 'oklch(0.80 0.16 25)' }}>Dôvod obmedzenia</div>
          <div className="fs-13 mt-1">{user.suspendReason}</div>
        </div>
      )}

      <div className="grid-2 mb-3" style={{ gap: 8 }}>
        <div className="glass-light p-3"><div className="text-3 fs-12">Agenti</div><div className="mono fw-600 fs-15">{user.agents}</div></div>
        <div className="glass-light p-3"><div className="text-3 fs-12">P&L</div><div className={`mono fw-600 fs-15 ${user.pnl>=0?'num-up':'num-down'}`}>{user.pnl===0?'—':fmtMoney(user.pnl)}</div></div>
        <div className="glass-light p-3"><div className="text-3 fs-12">Joined</div><div className="mono fs-13 mt-1">{user.joined}</div></div>
        <div className="glass-light p-3"><div className="text-3 fs-12">Last seen</div><div className="fs-13 mt-1">{user.lastSeen}</div></div>
      </div>

      <div className="fs-12 fw-600 text-2 mb-2" style={{ letterSpacing: '0.06em' }}>ZMENA TIERU</div>
      <div className="row gap-2 mb-4">
        {['basic','pro','elite'].map(t => (
          <button key={t} className={`pill ${user.tier===t?`pill-${t==='elite'?'amber':t==='pro'?'violet':'gray'}`:'pill-gray'} flex-1`}
            style={{ cursor: 'pointer', padding: '6px 8px', justifyContent: 'center' }}
            onClick={() => onSetTier(t)}>{t.toUpperCase()}</button>
        ))}
      </div>

      <div className="fs-12 fw-600 text-2 mb-2" style={{ letterSpacing: '0.06em' }}>AKCIE</div>
      <div className="col gap-2">
        {!user.verified && (
          <button className="btn btn-secondary" onClick={() => onAction('verify')}>
            <Icon name="check" size={14}/> Overiť usera
          </button>
        )}
        {user.status === 'active' && (
          <>
            <button className="btn btn-secondary" onClick={() => onAction('suspend')}>
              <Icon name="pause" size={14}/> Pozastaviť účet
            </button>
            <button className="btn btn-danger" onClick={() => onAction('ban')}>
              <Icon name="x" size={14}/> Zabanovať
            </button>
          </>
        )}
        {(user.status === 'suspended' || user.status === 'banned' || user.status === 'pending') && (
          <button className="btn btn-secondary" onClick={() => onAction('reactivate')}>
            <Icon name="check" size={14}/> Reaktivovať
          </button>
        )}
        <button className="btn btn-secondary"><Icon name="mail" size={14}/> Poslať email</button>
        <button className="btn btn-secondary"><Icon name="flag" size={14}/> Audit log</button>
        <button className="btn btn-danger" onClick={() => onAction('delete')}>
          <Icon name="trash" size={14}/> Vymazať data (GDPR)
        </button>
      </div>
    </div>
  );
}

function MarketplaceApproval({ onToast }) {
  const pending = [
    { id: 1, name: 'Volatility Tamer v2', author: 'm.kovac', symbol: 'BTC/USD', win: 73, submitted: '2026-05-01' },
    { id: 2, name: 'SOL Grid Master', author: 'crypto_jano', symbol: 'SOL/USD', win: 64, submitted: '2026-05-02' },
    { id: 3, name: 'NVDA Swing Pro', author: 'p.novak', symbol: 'NVDA', win: 71, submitted: '2026-05-03' },
    { id: 4, name: 'Multi-asset Hunter', author: 'tradergirl', symbol: 'Multi', win: 58, submitted: '2026-05-04' },
  ];
  return (
    <div className="glass" style={{ overflow: 'hidden' }}>
      <table className="tbl">
        <thead><tr><th>Agent</th><th>Autor</th><th>Symbol</th><th>Win</th><th>Submitted</th><th>Akcia</th></tr></thead>
        <tbody>
          {pending.map(p => (
            <tr key={p.id}>
              <td className="fw-500">{p.name}</td>
              <td>{p.author}</td>
              <td>{p.symbol}</td>
              <td className="mono num-up">{p.win}%</td>
              <td className="text-3 mono fs-12">{p.submitted}</td>
              <td>
                <div className="row gap-2">
                  <button className="pill pill-green" style={{ cursor: 'pointer' }} onClick={() => onToast(`Schválené: ${p.name}`)}>✓ Schváliť</button>
                  <button className="pill pill-red" style={{ cursor: 'pointer' }} onClick={() => onToast(`Zamietnuté: ${p.name}`)}>✗ Zamietnuť</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DemoAgents({ onToast }) {
  return (
    <div className="grid-3">
      {[1,2,3,4,5,6].map(i => (
        <div key={i} className="glass p-4">
          <div className="row between mb-2">
            <div className="fw-600">Demo Agent #{i}</div>
            <span className="dot dot-live"/>
          </div>
          <div className="text-3 fs-12 mb-3">Featured v marketplace</div>
          <div className="row gap-2">
            <button className="pill pill-gray flex-1" style={{ justifyContent: 'center', cursor: 'pointer' }}>Edit</button>
            <button className="pill pill-gray" style={{ cursor: 'pointer' }}><Icon name="pause" size={11}/></button>
          </div>
        </div>
      ))}
    </div>
  );
}

function SystemStats({ stats }) {
  return (
    <div className="grid-2" style={{ gap: 20 }}>
      <div className="glass p-5">
        <div className="fs-13 fw-600 mb-3" style={{ letterSpacing: '0.06em' }}>TIER DISTRIBÚCIA</div>
        {[['Basic', stats.basic, 'gray'], ['Pro', stats.pro, 'violet'], ['Elite', stats.elite, 'amber']].map(([l, n, c]) => (
          <div key={l} className="mb-3">
            <div className="row between fs-13 mb-1">
              <span>{l}</span>
              <span className="mono">{n} ({Math.round((n/stats.total)*100)}%)</span>
            </div>
            <div className="progress"><div className="progress-fill" style={{ width: `${(n/stats.total)*100}%`,
              background: c==='amber'?'oklch(0.82 0.14 75)':c==='violet'?'oklch(0.72 0.18 295)':'oklch(0.55 0.04 240)' }}/></div>
          </div>
        ))}
      </div>
      <div className="glass p-5">
        <div className="fs-13 fw-600 mb-3" style={{ letterSpacing: '0.06em' }}>SYSTÉMOVÝ STAV</div>
        {[
          ['Backend API', 'oper.', 'green'],
          ['PostgreSQL', '12ms latency', 'green'],
          ['Binance feed', 'real-time', 'green'],
          ['Telegram bot', '8 alerts/min', 'green'],
          ['Stripe webhooks', 'oper.', 'green'],
          ['Email queue', '142 in queue', 'amber'],
        ].map(([l, v, c]) => (
          <div key={l} className="row between" style={{ padding: '8px 0', borderBottom: '1px solid var(--border-1)' }}>
            <div className="row gap-2"><span className={`dot dot-${c==='green'?'live':'paused'}`}/>{l}</div>
            <span className="mono fs-13 text-2">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

window.HermesScreens2 = { Leaderboard, Backtest, AdminCMS };


const { useState, useEffect } = React;
const { TopNav, LoginScreen, DEMO_AGENTS } = window.Hermes;
const { Dashboard, Marketplace, AgentBuilder } = window.HermesScreens;
const { Leaderboard, Backtest, AdminCMS } = window.HermesScreens2;

function App() {
  const [user, setUser] = useState(null);
  const [page, setPage] = useState('dashboard');
  const [agents, setAgents] = useState(DEMO_AGENTS);
  const [toast, setToast] = useState(null);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2400);
  };

  React.useEffect(() => {
    function applySessionUser() {
      var st = typeof window.getHermesAuthState === 'function' ? window.getHermesAuthState() : null;
      if (!st || !st.authenticated) return;
      var email = st.email || st.username || '';
      var handle = st.username || (email.indexOf('@') > -1 ? email.split('@')[0] : email) || 'user';
      setUser({
        email: email || handle,
        handle: handle,
        tier: String(st.tier || 'basic').toLowerCase(),
        isAdmin: !!st.isAdmin,
      });
    }
    if (typeof window.checkAuthStatus !== 'function') return;
    window.checkAuthStatus().then(function () {
      applySessionUser();
      if (typeof window.loadDashboard === 'function') {
        return window.loadDashboard();
      }
    });
  }, []);

  const handleLogin = ({ email }) => {
    const isAdmin = email.includes('admin');
    setUser({
      email,
      handle: isAdmin ? 'admin' : 'jc.demo',
      tier: isAdmin ? 'admin' : 'pro',
      isAdmin,
    });
    setPage(isAdmin ? 'admin' : 'dashboard');
  };

  const handleLogout = () => { setUser(null); setPage('dashboard'); };

  const handleSubscribe = (agent) => {
    setAgents(prev => [...prev, {
      id: Date.now(), symbol: agent.symbol, name: agent.name,
      category: agent.symbol.includes('NVDA') || agent.symbol.includes('AAPL') ? 'stocks' : 'crypto',
      win: agent.win, pnl: 0, status: 'live', strategy: agent.strategy, risk: 'medium', trades: 0,
      sparks: [10,11,12,11,13,14,13,15,16,17,18,19],
    }]);
  };

  const handleCreate = (data) => {
    setAgents(prev => [...prev, {
      id: Date.now(), symbol: data.symbol, name: data.name,
      category: data.category === 'stocks' ? 'stocks' : data.category === 'commodities' ? 'commodities' : 'crypto',
      win: 50 + Math.floor(Math.random()*15), pnl: 0, status: 'live',
      strategy: data.strategy, risk: data.risk, trades: 0,
      sparks: [10,11,10,12,11,13,12,14,15,14,16,17],
    }]);
  };

  if (!user) return <LoginScreen onLogin={handleLogin}/>;

  return (
    <div className="app-container">
      <TopNav page={page} onNav={setPage} isAdmin={user.isAdmin} onLogout={handleLogout} user={user} notifCount={3}/>
      {page === 'dashboard' && <Dashboard user={user} onNav={setPage} agents={agents} setAgents={setAgents} onToast={showToast}/>}
      {page === 'marketplace' && <Marketplace onNav={setPage} onSubscribe={handleSubscribe} onToast={showToast}/>}
      {page === 'builder' && <AgentBuilder onNav={setPage} onCreate={handleCreate} onToast={showToast}/>}
      {page === 'leaderboard' && <Leaderboard user={user} onToast={showToast}/>}
      {page === 'backtest' && <Backtest user={user} onToast={showToast}/>}
      {page === 'admin' && user.isAdmin && <AdminCMS onToast={showToast} onNav={setPage}/>}

      <div className="footer">© 2026 Hermes Trading Agents · paper trading · žiadne reálne peniaze</div>

      {toast && (
        <div className="toast">
          <span style={{ color: 'oklch(0.85 0.14 155)' }}>●</span> {toast}
        </div>
      )}
    </div>
  );
}

function __hermesMountApp() {
  function run() {
    var __r = document.querySelector('#root');
    if (!__r) { console.error('[Hermes] #root missing'); return; }
    if (!window.ReactDOM || typeof window.ReactDOM.createRoot !== 'function') {
      console.error('[Hermes] ReactDOM.createRoot missing');
      return;
    }
    window.ReactDOM.createRoot(__r).render(<App/>);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { requestAnimationFrame(run); });
  } else {
    requestAnimationFrame(run);
  }
}

__hermesMountApp();
console.log('Babel done');
