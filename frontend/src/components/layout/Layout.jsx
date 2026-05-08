import BottomNav from "./BottomNav";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import TopNav from "./TopNav";
import { useBreakpoint } from "../../hooks/useBreakpoint";

export default function Layout({ page, setPage, user, onLogout, children }) {
  const { isDesktop } = useBreakpoint();
  return (
    <div className="app-layout">
      {isDesktop && <Sidebar page={page} onNav={setPage} user={user} onLogout={onLogout} />}
      <main className="main-content" style={{ marginLeft: isDesktop ? 240 : 0, paddingBottom: isDesktop ? 0 : "calc(64px + env(safe-area-inset-bottom))" }}>
        {isDesktop ? <TopBar page={page} user={user} onNav={setPage} /> : <TopNav user={user} onMore={() => setPage("backtest")} />}
        {children}
      </main>
      {!isDesktop && <BottomNav page={page} onNav={setPage} />}
    </div>
  );
}

