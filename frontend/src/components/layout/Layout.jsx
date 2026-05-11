import BottomNav from "./BottomNav";
import HermesTopNav from "./HermesTopNav";
import TopNav from "./TopNav";
import { useBreakpoint } from "../../hooks/useBreakpoint";
import { useTheme } from "../../hooks/useTheme";

export default function Layout({ page, setPage, user, onLogout, totalPnl = 0, children }) {
  const { isDesktop } = useBreakpoint();
  // Hermes is dark-only — no theme toggle in the UI. The hook is still
  // called so old `data-theme="light"` attributes get cleaned up on load.
  useTheme();

  const skipToMain = (e) => {
    e.preventDefault();
    const el = document.getElementById("main-content");
    el?.focus({ preventScroll: false });
  };

  return (
    <div className="app-layout app-layout--topnav">
      <a href="#main-content" className="skip-to-content" onClick={skipToMain}>
        Skip to main content
      </a>
      {isDesktop ? (
        <HermesTopNav
          page={page}
          user={user}
          onNav={setPage}
          onLogout={onLogout}
          totalPnl={totalPnl}
        />
      ) : (
        <TopNav user={user} onNav={setPage} totalPnl={totalPnl} />
      )}
      <main
        id="main-content"
        tabIndex={-1}
        className="main-content main-content--topnav"
        aria-label="Main content"
        style={{
          paddingBottom: isDesktop ? 0 : "calc(64px + env(safe-area-inset-bottom))",
          paddingTop: isDesktop ? undefined : "env(safe-area-inset-top, 0px)",
        }}
      >
        {children}
      </main>
      {!isDesktop && <BottomNav page={page} onNav={setPage} />}
    </div>
  );
}
