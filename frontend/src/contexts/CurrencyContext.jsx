import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { STORAGE_KEYS } from "../utils/storageKeys";

/**
 * Global currency context — lets the user pick a display currency
 * (USD / EUR / GBP / CZK). All monetary values across the app read
 * rates from here through `useCurrency()`.
 *
 * Conversion is always available (24/7) via cached or fallback rates.
 * Live rates are pulled from /api/exchange-rates on app start, every
 * hour while the tab is open, and whenever the tab regains focus,
 * so users see fresh values without ever needing to manually refresh.
 */

export const CURRENCY_OPTIONS = [
  { code: "USD", symbol: "$", name: "US Dollar" },
  { code: "EUR", symbol: "€", name: "Euro" },
  { code: "GBP", symbol: "£", name: "British Pound" },
  { code: "CZK", symbol: "Kč", name: "Czech Koruna" },
];

// Fallback rates vs USD (~Q2 2026). Used until /api/exchange-rates responds.
const FALLBACK_RATES_VS_USD = {
  USD: 1,
  EUR: 0.93,
  GBP: 0.79,
  CZK: 23.4,
};

const SYMBOL_BY_CODE = Object.fromEntries(
  CURRENCY_OPTIONS.map((o) => [o.code, o.symbol]),
);

const RATES_CACHE_KEY = "hermes:fxRates:v2";
// Cache TTL: 1 hour. We additionally refetch on tab focus so rates are
// effectively kept fresh 24/7 while the app is open.
const RATES_TTL_MS = 60 * 60 * 1000;
const RATES_POLL_INTERVAL_MS = 60 * 60 * 1000;

const CurrencyContext = createContext(null);

function loadStoredCode() {
  try {
    const v = window.localStorage.getItem(STORAGE_KEYS.CURRENCY);
    if (v && SYMBOL_BY_CODE[v]) return v;
  } catch {
    /* ignore */
  }
  return "USD";
}

function loadCachedRates() {
  try {
    const raw = window.localStorage.getItem(RATES_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.rates || !parsed?.fetchedAt) return null;
    if (Date.now() - parsed.fetchedAt > RATES_TTL_MS) return null;
    return parsed.rates;
  } catch {
    return null;
  }
}

function saveCachedRates(rates) {
  try {
    window.localStorage.setItem(
      RATES_CACHE_KEY,
      JSON.stringify({ rates, fetchedAt: Date.now() }),
    );
  } catch {
    /* ignore */
  }
}

export function CurrencyProvider({ children }) {
  const [code, setCode] = useState(loadStoredCode);
  const [rates, setRates] = useState(() => loadCachedRates() || FALLBACK_RATES_VS_USD);

  useEffect(() => {
    let cancelled = false;
    let timer = null;

    const fetchRates = async () => {
      try {
        const res = await fetch("/api/exchange-rates", { credentials: "include" });
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled || !data?.rates) return;
        const merged = { ...FALLBACK_RATES_VS_USD, ...data.rates, USD: 1 };
        setRates(merged);
        saveCachedRates(merged);
      } catch {
        /* keep fallback */
      }
    };

    fetchRates();
    timer = setInterval(fetchRates, RATES_POLL_INTERVAL_MS);
    const onVisibility = () => {
      if (document.visibilityState === "visible") fetchRates();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  const setCurrency = useCallback((nextCode) => {
    if (!SYMBOL_BY_CODE[nextCode]) return;
    setCode(nextCode);
    try {
      window.localStorage.setItem(STORAGE_KEYS.CURRENCY, nextCode);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(() => {
    const rate = rates[code] || 1;
    const symbol = SYMBOL_BY_CODE[code] || "$";

    /**
     * Format a USD value as the active currency.
     * @param {number|string} usd
     * @param {object} [opts]
     * @param {number} [opts.decimals=2]      Override decimals.
     * @param {boolean} [opts.compact=false]   Use 1.2k / 3.4M abbreviations.
     * @param {boolean} [opts.signed=false]    Force +/- sign.
     */
    const format = (usd, opts = {}) => {
      const num = Number(usd);
      if (!Number.isFinite(num)) return `${symbol}0.00`;
      const converted = num * rate;
      const abs = Math.abs(converted);
      const { decimals, compact = false, signed = false } = opts;
      let body;
      if (compact && abs >= 1000) {
        const units = [
          { v: 1e9, s: "B" },
          { v: 1e6, s: "M" },
          { v: 1e3, s: "K" },
        ];
        const u = units.find((x) => abs >= x.v);
        body = (abs / u.v).toFixed(abs / u.v >= 100 ? 0 : abs / u.v >= 10 ? 1 : 2) + u.s;
      } else {
        const dec = typeof decimals === "number" ? decimals : abs >= 1000 ? 0 : 2;
        body = abs.toLocaleString("en-US", {
          minimumFractionDigits: dec,
          maximumFractionDigits: dec,
        });
      }
      const sign = signed ? (converted < 0 ? "-" : "+") : converted < 0 ? "-" : "";
      // CZK uses a postfix symbol (e.g. "+199 Kč"); USD / EUR / GBP prefix.
      if (code === "CZK") {
        return `${sign}${body} ${symbol}`;
      }
      return `${sign}${symbol}${body}`;
    };

    return {
      code,
      symbol,
      rate,
      rates,
      options: CURRENCY_OPTIONS,
      setCurrency,
      format,
      /** Convert a USD value into the active currency (no formatting). */
      convert: (usd) => Number(usd) * rate,
    };
  }, [code, rates, setCurrency]);

  return <CurrencyContext.Provider value={value}>{children}</CurrencyContext.Provider>;
}

export function useCurrency() {
  const ctx = useContext(CurrencyContext);
  if (!ctx) {
    // Permissive fallback so components don't crash if the provider is missing.
    return {
      code: "USD",
      symbol: "$",
      rate: 1,
      rates: FALLBACK_RATES_VS_USD,
      options: CURRENCY_OPTIONS,
      setCurrency: () => {},
      format: (usd, opts = {}) => {
        const num = Number(usd);
        if (!Number.isFinite(num)) return "$0.00";
        const abs = Math.abs(num);
        const dec = typeof opts.decimals === "number" ? opts.decimals : abs >= 1000 ? 0 : 2;
        const body = abs.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
        const sign = opts.signed ? (num < 0 ? "-" : "+") : num < 0 ? "-" : "";
        return `${sign}$${body}`;
      },
      convert: (usd) => Number(usd),
    };
  }
  return ctx;
}
