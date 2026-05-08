import { useEffect, useRef } from "react";

import { sendNotification } from "../../utils/notifications";
import { sounds } from "../../utils/sounds";

export default function AlertBanner({ alert }) {
  const prevAlertKey = useRef("");

  useEffect(() => {
    if (!alert) return;
    const nextKey = `${alert.title || ""}::${alert.message || ""}`;
    if (nextKey && nextKey !== prevAlertKey.current) {
      sounds.alert();
      sendNotification("⚠️ Hermes Alert", alert.message || alert.title || "Alert detected");
      prevAlertKey.current = nextKey;
    }
  }, [alert]);

  if (!alert) return null;
  return (
    <div className="announcement-banner visible" role="alert">
      <div className="announcement-inner">
        <div>
          <strong>{alert.title}</strong>
          <p>{alert.message}</p>
        </div>
      </div>
    </div>
  );
}
