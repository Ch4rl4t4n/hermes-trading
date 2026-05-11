import { useState } from "react";
import { loginWithGoogle, register } from "../api/auth";

export default function Register({ onRegistered, onGoLogin }) {
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [verificationHint, setVerificationHint] = useState("");

  const handleSubmit = async () => {
    setError("");
    setVerificationHint("");
    setLoading(true);
    const result = await register({
      email: email.trim(),
      username: username.trim(),
      password,
      confirm_password: confirm,
    });
    setLoading(false);
    if (result.needsVerification) {
      setVerificationHint(result.message || "");
      return;
    }
    if (result.data) {
      onRegistered(result.data);
      return;
    }
    setError(result.error || "Registration failed");
  };

  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 16 }}>
      <section className="modal modal-auth modal-login-wrap" style={{ width: "min(94vw,460px)" }}>
        <div className="login-brand">HERMES</div>
        <div className="login-tagline">Let Agents Cook</div>

        <div className="input-group">
          <label className="input-label">Email</label>
          <input
            type="email"
            className="input-field"
            placeholder="you@example.com"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="input-group">
          <label className="input-label">Username</label>
          <input
            type="text"
            className="input-field"
            placeholder="trader_01"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <div className="fs-12 muted mt-1" style={{ opacity: 0.75 }}>
            3–20 characters: letters, numbers, underscore.
          </div>
        </div>
        <div className="input-group">
          <label className="input-label">Password</label>
          <input
            type="password"
            className="input-field"
            placeholder="••••••••••••"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <div className="input-group">
          <label className="input-label">Confirm password</label>
          <input
            type="password"
            className="input-field"
            placeholder="••••••••••••"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </div>

        <button className="btn" type="button" onClick={handleSubmit} disabled={loading}>
          {loading ? "Creating…" : "Create account"}
        </button>
        <div className="auth-divider" aria-hidden="true">
          <span>or</span>
        </div>
        <button type="button" className="google-signin-btn" disabled={loading} onClick={() => loginWithGoogle()}>
          Continue with Google
        </button>

        {verificationHint ? (
          <div className="glass mt-2 p-2 fs-13" style={{ borderRadius: 8 }}>
            {verificationHint}
          </div>
        ) : null}
        {error ? <div className="error-msg active">{error}</div> : null}

        <div className="auth-switch">
          <span>
            Already have an account?{" "}
            <a
              href="#"
              onClick={(e) => {
                e.preventDefault();
                onGoLogin();
              }}
            >
              Sign in
            </a>
          </span>
        </div>
      </section>
    </main>
  );
}
