import { useState } from "react";
import { loginWithEmail, loginWithGoogle } from "../api/auth";

export default function Login({ onLogin, onGoRegister }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    setLoading(true);
    setError("");
    const result = await loginWithEmail(email, password);
    if (result.data) {
      onLogin(result.data);
    } else {
      setError(result.error);
    }
    setLoading(false);
  };

  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 16 }}>
      <section className="modal modal-auth modal-login-wrap" style={{ width: "min(94vw,460px)" }}>
        <div className="login-brand">HERMES</div>
        <div className="login-tagline">Let Agents Cook</div>

        <div className="input-group">
          <label className="input-label">Email or username</label>
          <input type="text" className="input-field" placeholder="Email or username" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
        </div>
        <div className="input-group">
          <label className="input-label">Password</label>
          <input type="password" className="input-field" placeholder="••••••••••••" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>

        <button className="btn" type="button" onClick={handleSubmit} disabled={loading}>
          {loading ? "Signing in..." : "Sign in"}
        </button>
        <div className="auth-divider" aria-hidden="true">
          <span>or</span>
        </div>
        <button type="button" className="google-signin-btn" onClick={loginWithGoogle}>
          Continue with Google
        </button>
        {error ? <div className="error-msg active">{error}</div> : null}
        <div className="auth-switch">
          <span>
            New here?{" "}
            <a
              href="/register"
              onClick={(e) => {
                e.preventDefault();
                if (onGoRegister) onGoRegister();
              }}
            >
              Create an account
            </a>
          </span>
          <span>
            <a href="#">Forgot password?</a>
          </span>
        </div>
      </section>
    </main>
  );
}

