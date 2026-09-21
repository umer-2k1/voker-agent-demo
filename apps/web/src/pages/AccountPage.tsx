import { Link } from "react-router-dom";

export type Account = {
  id: string;
  email: string;
  display_name: string | null;
};

export function AccountPage({ account }: { account: Account }) {
  return (
    <main className="settings-page">
      <p className="eyebrow">Account settings</p>
      <h1>Your account</h1>
      <section className="account-card">
        <b>{account.display_name ?? "Google account"}</b>
        <span>{account.email}</span>
      </section>
      <Link className="settings-link" to="/settings">
        Manage project API keys
      </Link>
    </main>
  );
}
