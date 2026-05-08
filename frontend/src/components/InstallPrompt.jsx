import { useEffect, useState } from "react";
import { STORAGE_KEYS } from "../utils/storageKeys";

function safeGetDismissed() {
  try {
    return window.localStorage.getItem(STORAGE_KEYS.INSTALL_DISMISSED) === "true";
  } catch {
    return false;
  }
}

function safeSetDismissed() {
  try {
    window.localStorage.setItem(STORAGE_KEYS.INSTALL_DISMISSED, "true");
  } catch {
    // Ignore storage failures.
  }
}

export default function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [dismissed, setDismissed] = useState(() => safeGetDismissed());
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" ? window.innerWidth < 768 : false);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 768);
    const onBeforeInstallPrompt = (event) => {
      event.preventDefault();
      setDeferredPrompt(event);
    };
    const onAppInstalled = () => {
      setDeferredPrompt(null);
      setDismissed(true);
      safeSetDismissed();
    };

    window.addEventListener("resize", onResize);
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onAppInstalled);

    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onAppInstalled);
    };
  }, []);

  const handleInstall = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    try {
      await deferredPrompt.userChoice;
    } catch {
      // Ignore prompt errors on unsupported devices.
    }
    setDeferredPrompt(null);
    setDismissed(true);
    safeSetDismissed();
  };

  if (!isMobile || !deferredPrompt || dismissed) return null;

  return (
    <div className="install-prompt" role="dialog" aria-label="Install Hermes">
      <span className="install-prompt-text">Add Hermes to Home Screen</span>
      <div className="install-prompt-actions">
        <button type="button" className="install-prompt-btn" onClick={handleInstall}>
          Install
        </button>
        <button
          type="button"
          className="install-prompt-close"
          aria-label="Dismiss install prompt"
          onClick={() => {
            setDismissed(true);
            safeSetDismissed();
          }}
        >
          ×
        </button>
      </div>
    </div>
  );
}
