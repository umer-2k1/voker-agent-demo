import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  BarChart3,
  Bot,
  ClipboardCheck,
  Headphones,
  LayoutDashboard,
  PlugZap,
  Settings,
  Users,
} from "lucide-react";

import type { Account } from "@/pages/AccountPage";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8001";

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
        <p className="workspace">VOICE OPERATIONS</p>
        <nav aria-label="Primary navigation">
          <NavLink
            end
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            to="/"
          >
            <LayoutDashboard aria-hidden="true" size={16} />
            Overview
          </NavLink>
          <NavLink
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            to="/sessions"
          >
            <Headphones aria-hidden="true" size={16} />
            Sessions
          </NavLink>
          <NavLink
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            to="/#insights"
          >
            <BarChart3 aria-hidden="true" size={16} />
            Intelligence
          </NavLink>
          <NavLink
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            to="/setup"
          >
            <PlugZap aria-hidden="true" size={16} />
            Setup
          </NavLink>
          <span className="nav-item nav-item-muted">
            <Bot aria-hidden="true" size={16} /> Agents
          </span>
          <span className="nav-item nav-item-muted">
            <ClipboardCheck aria-hidden="true" size={16} /> Evaluations
          </span>
          <span className="nav-item nav-item-muted">
            <Users aria-hidden="true" size={16} /> Team
          </span>
          <NavLink
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            to="/settings"
          >
            <Settings aria-hidden="true" size={16} />
            Workspace settings
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
          <Button
            variant="ghost"
            size="sm"
            className="signout-button"
            disabled={logout.isPending}
            onClick={() => logout.mutate()}
          >
            {logout.isPending ? "Signing out…" : "Sign out"}
          </Button>
          {logout.isError ? (
            <small>Could not sign out. Try again.</small>
          ) : null}
        </div>
      </aside>
      <header className="mobile-dashboard-nav">
        <NavLink className="mobile-brand" to="/">
          <span className="brand-mark">V</span>
          <span>Voker</span>
        </NavLink>
        <nav aria-label="Mobile navigation">
          <NavLink end to="/">
            Overview
          </NavLink>
          <NavLink to="/sessions">Sessions</NavLink>
          <NavLink to="/settings">Settings</NavLink>
          <NavLink to="/setup">Setup</NavLink>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                className="mobile-avatar"
                size="icon-sm"
                variant="ghost"
                aria-label="Account menu"
              >
                {initials(account)}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>
                {account.display_name ?? account.email}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => navigate("/settings#profile")}>
                Profile settings
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={logout.isPending}
                onSelect={() => logout.mutate()}
                variant="destructive"
              >
                {logout.isPending ? "Signing out…" : "Sign out"}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </nav>
      </header>
      <Outlet />
    </main>
  );
}
