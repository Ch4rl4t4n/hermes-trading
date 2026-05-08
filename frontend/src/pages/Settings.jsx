import { useState } from "react";

import { useVoice } from "../hooks/useVoice";
import { requestPermission } from "../utils/notifications";
import { STORAGE_KEYS } from "../utils/storageKeys";

export default function Settings() {
  const { isSupported } = useVoice();
  const [voiceEnabled, setVoiceEnabled] = useState(() => {
    const raw = window.localStorage.getItem(STORAGE_KEYS.VOICE_ENABLED);
    return raw === null ? true : raw === "true";
  });
  const [notificationState, setNotificationState] = useState(() => {
    if (!("Notification" in window)) return "unsupported";
    return Notification.permission;
  });

  const onToggleVoice = (nextValue) => {
    setVoiceEnabled(nextValue);
    window.localStorage.setItem(STORAGE_KEYS.VOICE_ENABLED, String(nextValue));
  };

  const onEnableNotifications = async () => {
    if (!("Notification" in window)) {
      setNotificationState("unsupported");
      return;
    }
    const granted = await requestPermission();
    if (granted) {
      setNotificationState("granted");
      return;
    }
    setNotificationState(Notification.permission);
  };

  return (
    <section className="page-content">
      <article className="glass settings-card" style={{ padding: 16, maxWidth: 760 }}>
        <h3 style={{ marginTop: 0, marginBottom: 10 }}>Settings</h3>
        <div className="settings-row">
          <div className="settings-row-info">
            <strong className="settings-label">
              Agent Voice {!isSupported.tts ? <span className="text-3">(not supported by browser)</span> : null}
            </strong>
            <span className="settings-desc">Agent speaks after profitable trades</span>
          </div>
          <button
            type="button"
            className={`pill ${voiceEnabled ? "pill-violet" : "pill-gray"}`}
            onClick={() => onToggleVoice(!voiceEnabled)}
            disabled={!isSupported.tts}
            style={{ border: "none", minWidth: 70 }}
          >
            {voiceEnabled ? "On" : "Off"}
          </button>
        </div>

        <div className="settings-row" style={{ marginTop: 14 }}>
          <div className="settings-row-info">
            <strong className="settings-label">Notifications</strong>
            <span className="settings-desc">Browser notifications for alerts and profitable trades</span>
          </div>
          <div className="col" style={{ alignItems: "flex-end", gap: 6 }}>
            <button
              type="button"
              className="pill pill-violet"
              style={{ border: "none", minWidth: 170 }}
              onClick={onEnableNotifications}
              disabled={notificationState === "unsupported" || notificationState === "granted"}
            >
              Enable Notifications
            </button>
            {notificationState === "granted" ? <span className="text-3 fs-12">✓ Notifications enabled</span> : null}
            {notificationState === "denied" ? <span className="text-3 fs-12">Blocked in browser settings</span> : null}
            {notificationState === "unsupported" ? <span className="text-3 fs-12">Not supported by browser</span> : null}
          </div>
        </div>
      </article>
    </section>
  );
}
