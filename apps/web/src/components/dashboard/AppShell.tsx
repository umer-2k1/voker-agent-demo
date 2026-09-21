import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import type { Account } from "@/pages/AccountPage";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001";

function initials(account: Account) {
  const value = account.display_name?.trim() || account.email;
  return value
    .split(/\s+|@/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

export function AppShell({ account }: { account: Account }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logout = useMutation({
    mutationFn: async () => {
      const response = await fetch(`${apiBaseUrl}/auth/logout`, {
        credentials: "include",
        method: "POST",
      });
      if (!response.ok) throw new Error("Unable to sign out");
    },
    onSuccess: () => {
      queryClient.setQueryData(["account"], null);
      navigate("/login", { replace: true });
    },
  });
  return (
    <main className="product-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">V</span>
          <span>Voker</span>
        </div>
        <p className="workspace">VOICE INTELLIGENCE</p>
        <nav aria-label="Primary navigation">
          <NavLink
            end
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            to="/"
          >
            Overview
          </NavLink>
          <a className="nav-item" href="/#sessions">
            Sessions
          </a>
          <a className="nav-item" href="/#trace">
            Trace explorer
          </a>
          <a className="nav-item" href="/#insights">
            Intelligence
          </a>
          <NavLink
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            to="/settings"
          >
            Project settings
          </NavLink>
          <NavLink
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            to="/account"
          >
            Account
          </NavLink>
        </nav>
        <div className="sidebar-foot account-menu">
          <span className="account-avatar" aria-hidden="true">
            {initials(account)}
          </span>
          <div>
            <b>{account.display_name ?? "Google account"}</b>
            <span>{account.email}</span>
          </div>
          <button
            className="signout-button"
            disabled={logout.isPending}
            onClick={() => logout.mutate()}
          >
            {logout.isPending ? "Signing out…" : "Sign out"}
          </button>
          {logout.isError ? (
            <small>Could not sign out. Try again.</small>
          ) : null}
        </div>
      </aside>
      <Outlet />
    </main>
  );
}
