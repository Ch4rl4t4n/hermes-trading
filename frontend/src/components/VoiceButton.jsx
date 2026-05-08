import { useEffect, useMemo, useState } from "react";

import { useVoice } from "../hooks/useVoice";

export default function VoiceButton({ onTranscript, size = "md", disabled = false }) {
  const { startListening, stopListening, isSupported } = useVoice();
  const [status, setStatus] = useState("idle"); // idle | listening | processing

  const buttonSize = useMemo(() => {
    if (size === "sm") return 38;
    if (size === "lg") return 52;
    return 44;
  }, [size]);

  const canUse = isSupported.stt && !disabled;

  const handleClick = async () => {
    if (!canUse) return;

    if (status === "listening") {
      stopListening();
      setStatus("idle");
      return;
    }

    setStatus("listening");
    try {
      const transcript = await startListening();
      if (!transcript) {
        setStatus("idle");
        return;
      }
      setStatus("processing");
      await onTranscript?.(transcript);
      setStatus("idle");
    } catch {
      setStatus("idle");
    }
  };

  const className = `voice-btn voice-btn-${status} ${!canUse ? "voice-btn-disabled" : ""}`;

  useEffect(
    () => () => {
      stopListening();
    },
    [stopListening],
  );

  return (
    <div className="voice-btn-wrap" title={!isSupported.stt ? "Not supported" : ""}>
      <button
        type="button"
        className={className}
        onClick={handleClick}
        disabled={!canUse || status === "processing"}
        style={{ width: buttonSize, height: buttonSize }}
        aria-label="Voice input"
      >
        {status === "processing" ? <span className="voice-spinner" /> : <span className="voice-icon">🎤</span>}
      </button>
      {status === "listening" ? <span className="voice-listening-label">Listening...</span> : null}
    </div>
  );
}
