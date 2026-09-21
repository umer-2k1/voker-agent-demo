const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001";

function GoogleMark() {
  return (
    <svg aria-hidden="true" height="20" viewBox="0 0 24 24" width="20">
      <path
        fill="#4285F4"
        d="M21.35 12.23c0-.72-.06-1.25-.2-1.8H12v3.35h5.37c-.11.83-.72 2.08-2.08 2.92l-.02.11 3.02 2.28.21.02c1.93-1.73 2.85-4.28 2.85-6.88Z"
      />
      <path
        fill="#34A853"
        d="M12 21.5c2.63 0 4.84-.85 6.45-2.31l-3.07-2.41c-.82.56-1.92.95-3.38.95a5.86 5.86 0 0 1-5.55-3.96l-.11.01-3.14 2.37-.04.1A9.72 9.72 0 0 0 12 21.5Z"
      />
      <path
        fill="#FBBC05"
        d="M6.45 13.77A5.72 5.72 0 0 1 6.13 12c0-.62.12-1.22.31-1.77v-.12L3.27 7.7l-.1.05A9.28 9.28 0 0 0 2.1 12c0 1.53.37 2.98 1.07 4.25l3.28-2.48Z"
      />
      <path
        fill="#EA4335"
        d="M12 6.27c1.84 0 3.08.77 3.79 1.42l2.77-2.63C16.83 3.53 14.63 2.5 12 2.5a9.72 9.72 0 0 0-8.84 5.25l3.28 2.48A5.88 5.88 0 0 1 12 6.27Z"
      />
    </svg>
  );
}

export function LoginPage() {
  return (
    <main className="login-page">
      <section className="login-story">
        <div className="login-brand">
          <span className="brand-mark">V</span>
          <span>Voker</span>
        </div>
        <div className="login-story-copy">
          <p className="eyebrow">Voice intelligence</p>
          <h1>Every voice-agent decision, grounded in its trace.</h1>
          <p>
            Understand calls, investigate failures, and keep the evidence behind
            each conclusion in one trusted workspace.
          </p>
        </div>
        <ul className="login-benefits">
          <li>
            <i>✓</i>
            <span>Timeline, transcript, playback, and event evidence</span>
          </li>
          <li>
            <i>✓</i>
            <span>Session intelligence without unsupported claims</span>
          </li>
          <li>
            <i>✓</i>
            <span>Project-scoped keys and access controls</span>
          </li>
        </ul>
        <div className="login-glow login-glow-one" />
        <div className="login-glow login-glow-two" />
      </section>
      <section className="login-panel">
        <div className="login-card">
          <div className="login-card-brand">
            <span className="brand-mark">V</span>
            <span>Voker Voice</span>
          </div>
          <p className="eyebrow">Secure workspace</p>
          <h2>Welcome back</h2>
          <p className="login-copy">
            Sign in with your approved Google account to continue to your voice
            intelligence workspace.
          </p>
          <a className="google-login" href={`${apiBaseUrl}/auth/google/login`}>
            <GoogleMark />
            Continue with Google
          </a>
          <p className="login-help">
            Your organization controls access. We only request your basic Google
            profile to create your secure session.
          </p>
        </div>
        <p className="login-footer">
          Protected by signed sessions · Evidence stays project-scoped
        </p>
      </section>
    </main>
  );
}
