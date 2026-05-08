import { useMemo, useState } from "react";
import { STORAGE_KEYS } from "../utils/storageKeys";

const QUOTES = [
  { quote: "The trend is your friend.", author: "Jesse Livermore" },
  { quote: "Cut your losses short and let your profits run.", author: "David Ricardo" },
  { quote: "Risk comes from not knowing what you're doing.", author: "Warren Buffett" },
  { quote: "The market is a device for transferring money from the impatient to the patient.", author: "Warren Buffett" },
  { quote: "In trading, the impossible happens about twice a year.", author: "Henri M. Simoes" },
  { quote: "It's not about being right. It's about making money.", author: "George Soros" },
  { quote: "Plan the trade and trade the plan.", author: "Unknown" },
  { quote: "Markets are never wrong, opinions often are.", author: "Jesse Livermore" },
  { quote: "Opportunities are rare. When it rains gold, put out the bucket.", author: "Warren Buffett" },
  { quote: "The goal is not to be right, but to make money.", author: "Marty Schwartz" },
];

function dayOfYear(date) {
  const start = new Date(date.getFullYear(), 0, 0);
  const diff = date - start;
  const oneDay = 1000 * 60 * 60 * 24;
  return Math.floor(diff / oneDay);
}

export default function TradingQuote({ isEmpty = false }) {
  const [collapsed, setCollapsed] = useState(() => window.localStorage.getItem(STORAGE_KEYS.QUOTE_COLLAPSED) === "true");

  const todayQuote = useMemo(() => {
    const idx = dayOfYear(new Date()) % QUOTES.length;
    return QUOTES[idx];
  }, []);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    window.localStorage.setItem(STORAGE_KEYS.QUOTE_COLLAPSED, String(next));
  };

  return (
    <article
      className={`trading-quote-card glass ${collapsed ? "collapsed" : ""} ${isEmpty ? "empty" : ""}`}
      onClick={toggle}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && toggle()}
    >
      <div className="trading-quote-title">Daily Trading Quote</div>
      {!collapsed ? (
        <>
          <p className="trading-quote-text">"{todayQuote.quote}"</p>
          <div className="trading-quote-author">— {todayQuote.author}</div>
        </>
      ) : (
        <div className="trading-quote-mini">{todayQuote.quote}</div>
      )}
    </article>
  );
}
