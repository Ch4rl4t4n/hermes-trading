import BottomNav from "./BottomNav";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import TopNav from "./TopNav";
import { useBreakpoint } from "../../hooks/useBreakpoint";
import { useTheme } from "../../hooks/useTheme";

export default function Layout({ page, setPage, user, onLogout, children }) {
  const { isDesktop } = useBreakpoint();
  const { theme, isLight, toggleTheme } = useTheme();

  const skipToMain = (e) => {
    e.preventDefault();
    const el = document.getElementById("main-content");
    el?.focus({ preventScroll: false });
  };

  return (
    <div className="app-layout">
      <a href="#main-content" className="skip-to-content" onClick={skipToMain}>
        Preskočiť na hlavný obsah
      </a>
      {isDesktop && <Sidebar page={page} onNav={setPage} user={user} onLogout={onLogout} />}
      <main
        id="main-content"
        tabIndex={-1}
        className="main-content"
        aria-label="Hlavný obsah"
        style={{ marginLeft: isDesktop ? 240 : 0, paddingBottom: isDesktop ? 0 : "calc(64px + env(safe-area-inset-bottom))" }}
      >
        {isDesktop ? (
          <TopBar page={page} user={user} onNav={setPage} theme={theme} isLight={isLight} onToggleTheme={toggleTheme} />
        ) : (
          <TopNav user={user} onMore={() => setPage("backtest")} theme={theme} isLight={isLight} onToggleTheme={toggleTheme} />
        )}
        {children}
      </main>
      {!isDesktop && <BottomNav page={page} onNav={setPage} />}
    </div>
  );
}

