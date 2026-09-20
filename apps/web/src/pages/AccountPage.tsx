import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001";

type Account = { id: string; email: string; display_name: string | null };

export function AccountPage() {
  const navigate = useNavigate();
  const account = useQuery({
    queryKey: ["account"],
    queryFn: async () => {
      const response = await fetch(`${apiBaseUrl}/auth/me`, { credentials: "include" });
      if (!response.ok) throw new Error("Sign in required");
      return response.json() as Promise<Account>;
    },
  });
  const logout = useMutation({
    mutationFn: () => fetch(`${apiBaseUrl}/auth/logout`, { credentials: "include", method: "POST" }),
    onSuccess: () => navigate("/"),
  });
  return <main className="settings-page"><p className="eyebrow">Account settings</p><h1>Your account</h1>{account.isPending ? <div className="skeleton-list"><i /><i /></div> : null}{account.isError ? <p className="connection-error">Sign in is required. <a href={`${apiBaseUrl}/auth/google/login`}>Continue with Google</a></p> : null}{account.data ? <section className="account-card"><b>{account.data.display_name ?? "Google account"}</b><span>{account.data.email}</span><button onClick={() => logout.mutate()} disabled={logout.isPending}>Sign out</button></section> : null}<Link className="settings-link" to="/settings">Manage project API keys</Link></main>;
}
