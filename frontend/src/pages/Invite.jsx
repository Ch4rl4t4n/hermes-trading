import { useCallback, useEffect, useState } from "react";
import client from "../api/client";

/**
 * Referral / rewards landing page (eToro-style invite flow).
 * Data: GET /api/sharing/referral-info — referral_url, referral_code, referral_count, bonus_active.
 * Reward model: +3 agent slots for 30 days (see core/referral_helpers.py), not stock grants.
 */

export default function Invite({ onToast, onNav }) {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copyState, setCopyState] = useState("idle");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await client.get("/api/sharing/referral-info");
      if (data?.error) {
        onToast?.(data.error);
        setInfo(null);
        return;
      }
      setInfo(data);
    } catch (err) {
      onToast?.(err?.response?.data?.error || "Could not load invite link.");
      setInfo(null);
    } finally {
      setLoading(false);
    }
  }, [onToast]);

  useEffect(() => {
    load();
  }, [load]);

  const onCopy = async () => {
    const url = info?.referral_url;
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopyState("done");
      onToast?.("Link copied to clipboard");
      setTimeout(() => setCopyState("idle"), 2000);
    } catch {
      onToast?.("Copy failed — select the link and copy manually.");
    }
  };

  return (
    <section className="page-content hermes-invite col" style={{ gap: 20, maxWidth: 720, margin: "0 auto" }}>
      <header className="hermes-page-head" style={{ marginBottom: 0 }}>
        <div>
          <h1 className="hermes-page-title">Invite &amp; rewards</h1>
          <p className="hermes-page-lead">Share Hermes. You and your friends can unlock extra agent capacity.</p>
        </div>
      </header>

      <article className="hermes-invite-hero">
        <div className="hermes-invite-hero-grid">
          <div className="hermes-invite-hero-copy">
            <h2 className="hermes-invite-title">Invite friends and earn bonus slots</h2>
            <p className="hermes-invite-lead">
              When someone joins with your link and completes their first sign-in, both of you get{" "}
              <strong>+3 extra marketplace agent slots for 30 days</strong> (stackable with your tier).
            </p>
            {loading ? (
              <p className="text-3 fs-12" style={{ marginTop: 12 }}>Loading your link…</p>
            ) : info?.referral_url ? (
              <>
                <p className="hermes-invite-label">Share your link</p>
                <div className="hermes-invite-link-row">
                  <div className="hermes-invite-link-field" title={info.referral_url}>
                    <span className="hermes-invite-link-text">{info.referral_url}</span>
                  </div>
                  <button
                    type="button"
                    className="hermes-invite-copy"
                    onClick={onCopy}
                    disabled={!info.referral_url}
                  >
                    {copyState === "done" ? "Copied" : "Copy"}
                  </button>
                </div>
                <p className="hermes-invite-disclaimer">
                  This program is subject to our{" "}
                  <a href="https://letagentscook.lol/terms" rel="noreferrer" target="_blank" className="hermes-invite-terms">
                    Terms &amp; Conditions
                  </a>
                  . Future cash or credit rewards may be added in the Rewards section.
                </p>
              </>
            ) : (
              <p className="text-3">We could not load your referral link. Try again from Settings.</p>
            )}
            {info?.referral_count != null ? (
              <p className="hermes-invite-stats">
                <strong className="mono">{info.referral_count}</strong>{" "}
                {info.referral_count === 1 ? "friend has" : "friends have"} used your code so far.
                {info.bonus_active && info.bonus_expires_at ? (
                  <span className="hermes-invite-bonus-pill">
                    Referral bonus active — slots expire {new Date(info.bonus_expires_at).toLocaleDateString("en-US")}
                  </span>
                ) : null}
              </p>
            ) : null}
          </div>
          <div className="hermes-invite-hero-art" aria-hidden="true">
            <div className="hermes-invite-iso">
              <div className="hermes-invite-iso-base" />
              <div className="hermes-invite-iso-figure" />
            </div>
          </div>
        </div>
      </article>

      <article className="hermes-invite-how">
        <h2 className="hermes-invite-how-title">How it works</h2>
        <p className="hermes-invite-how-lead">
          Invite your friends. Rewards unlock automatically after they complete signup and first login (deposit optional — Hermes is paper-first).
        </p>
        <div className="hermes-invite-steps">
          <div className="hermes-invite-step">
            <div className="hermes-invite-step-icon" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2 11 13" />
                <path d="M22 2 15 22 11 13 2 9 22 2z" />
              </svg>
            </div>
            <strong>Share your link</strong>
            <span className="text-3 fs-12">Send your personal URL anywhere — chat, email, or social.</span>
          </div>
          <div className="hermes-invite-dash" aria-hidden="true" />
          <div className="hermes-invite-step">
            <div className="hermes-invite-step-icon" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect x="5" y="2" width="14" height="20" rx="2" />
                <path d="M12 18h.01" />
              </svg>
            </div>
            <strong>Friends register</strong>
            <span className="text-3 fs-12">They create an account; your code connects them to you.</span>
          </div>
          <div className="hermes-invite-dash" aria-hidden="true" />
          <div className="hermes-invite-step">
            <div className="hermes-invite-step-icon" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
            </div>
            <strong>Both earn rewards</strong>
            <span className="text-3 fs-12">After first login, +3 bonus agent slots for 30 days for each of you.</span>
          </div>
        </div>
      </article>

      <div className="hermes-invite-footer-actions">
        <button type="button" className="hermes-cta-pill" onClick={() => onNav?.("marketplace")}>
          Explore marketplace
        </button>
        <button type="button" className="hermes-invite-ghost" onClick={() => onNav?.("settings")}>
          Back to settings
        </button>
      </div>
    </section>
  );
}
