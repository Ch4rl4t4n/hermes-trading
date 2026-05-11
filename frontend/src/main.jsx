import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { CurrencyProvider } from "./contexts/CurrencyContext.jsx";
import "./styles/globals.css";

const rootEl = document.getElementById("root");

if (!rootEl) throw new Error("Missing root element");

createRoot(rootEl).render(
  <StrictMode>
    <CurrencyProvider>
      <App />
    </CurrencyProvider>
  </StrictMode>,
);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}
