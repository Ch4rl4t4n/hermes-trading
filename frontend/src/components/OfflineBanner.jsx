import { useEffect, useState } from "react";

export default function OfflineBanner() {
  const [offline, setOffline] = useState(typeof navigator !== "undefined" ? !navigator.onLine : false);
  const [visible, setVisible] = useState(typeof navigator !== "undefined" ? !navigator.onLine : false);

  useEffect(() => {
    let hideTimer = null;
    const onOffline = () => {
      if (hideTimer) {
        window.clearTimeout(hideTimer);
        hideTimer = null;
      }
      setOffline(true);
      setVisible(true);
    };
    const onOnline = () => {
      setOffline(false);
      hideTimer = window.setTimeout(() => setVisible(false), 220);
    };
    window.addEventListener("offline", onOffline);
    window.addEventListener("online", onOnline);
    return () => {
      if (hideTimer) {
        window.clearTimeout(hideTimer);
      }
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("online", onOnline);
    };
  }, []);

  if (!visible) return null;

  return (
    <div className={`offline-banner ${offline ? "show" : "hide"}`} role="status">
      ⚡ Offline — showing cached data
    </div>
  );
}
