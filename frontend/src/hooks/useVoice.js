import { useCallback, useEffect, useMemo, useRef } from "react";

export function useVoice() {
  const synthRef = useRef(typeof window !== "undefined" ? window.speechSynthesis : null);
  const recognitionRef = useRef(null);

  const isSupported = useMemo(() => {
    if (typeof window === "undefined") {
      return { tts: false, stt: false };
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    return {
      tts: Boolean(window.speechSynthesis),
      stt: Boolean(SpeechRecognition),
    };
  }, []);

  const speak = useCallback((text, options = {}) => {
    if (!synthRef.current || !text) return;
    const utterance = new SpeechSynthesisUtterance(String(text));
    utterance.rate = Number(options.rate ?? 0.95);
    utterance.pitch = Number(options.pitch ?? 1.0);
    utterance.volume = Number(options.volume ?? 0.8);
    utterance.lang = String(options.lang ?? "en-US");
    synthRef.current.cancel();
    synthRef.current.speak(utterance);
  }, []);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // Ignore stop errors.
      }
      recognitionRef.current = null;
    }
  }, []);

  const startListening = useCallback(
    (onResult, onError) =>
      new Promise((resolve, reject) => {
        if (typeof window === "undefined") {
          const err = new Error("Speech recognition unavailable");
          onError?.(err);
          reject(err);
          return;
        }
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
          const err = new Error("Speech recognition not supported");
          onError?.(err);
          reject(err);
          return;
        }

        stopListening();
        const recognition = new SpeechRecognition();
        recognitionRef.current = recognition;
        recognition.lang = "en-US";
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        recognition.continuous = false;

        recognition.onresult = (event) => {
          const transcript = String(event?.results?.[0]?.[0]?.transcript || "").trim();
          if (transcript) onResult?.(transcript);
          resolve(transcript);
        };
        recognition.onerror = (event) => {
          const err = new Error(event?.error || "voice_error");
          onError?.(err);
          reject(err);
        };
        recognition.onend = () => {
          recognitionRef.current = null;
        };

        try {
          recognition.start();
        } catch (err) {
          onError?.(err);
          reject(err);
        }
      }),
    [stopListening],
  );

  useEffect(
    () => () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch {
          // noop
        }
        recognitionRef.current = null;
      }
      if (synthRef.current) {
        synthRef.current.cancel();
      }
    },
    [],
  );

  return { speak, startListening, stopListening, isSupported };
}
