const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001";

export function LoginPage() {
  return <main className="login-page"><section className="login-card"><span className="brand-mark">V</span><p className="eyebrow">Voker Voice</p><h1>Sign in to your workspace</h1><p>Use your approved Google account to view project traces, settings, and API keys.</p><a className="google-login" href={`${apiBaseUrl}/auth/google/login`}>Continue with Google</a></section></main>;
}
