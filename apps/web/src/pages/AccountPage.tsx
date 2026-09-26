import { Link } from "react-router-dom";

import { Eyebrow, H1 } from "@/components/ui/typography";

export type Account = {
  id: string;
  email: string;
  display_name: string | null;
};

export function AccountPage({ account }: { account: Account }) {
  return (
    <main className="settings-page">
      <Eyebrow>Account settings</Eyebrow>
      <H1>Your account</H1>
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
