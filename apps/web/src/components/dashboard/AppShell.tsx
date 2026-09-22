import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { CSSProperties } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3,
  Bot,
  Headphones,
  LayoutDashboard,
  PlugZap,
  Settings,
} from "lucide-react";

import type { Account } from "@/pages/AccountPage";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8001";

const navigation = [
  { label: "Overview", to: "/", icon: LayoutDashboard, end: true },
  { label: "Sessions", to: "/sessions", icon: Headphones, end: false },
  { label: "Intents", to: "/intents", icon: BarChart3, end: false },
  { label: "Setup", to: "/setup", icon: PlugZap, end: false },
  { label: "Agents", to: "/agents", icon: Bot, end: false },
  { label: "Workspace settings", to: "/settings", icon: Settings, end: false },
] as const;

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

type DashboardSidebarProps = {
  account: Account;
  isSigningOut: boolean;
  logoutFailed: boolean;
  onLogout: () => void;
};

function DashboardSidebar({
  account,
  isSigningOut,
  logoutFailed,
  onLogout,
}: DashboardSidebarProps) {
  const location = useLocation();
  const { setOpenMobile } = useSidebar();

  return (
    <Sidebar
      aria-label="Primary navigation"
      className="voker-sidebar"
      collapsible="offcanvas"
    >
      <SidebarHeader className="voker-sidebar-header">
        <NavLink
          aria-label="Voker overview"
          className="brand"
          onClick={() => setOpenMobile(false)}
          to="/"
        >
          <span className="brand-mark" aria-hidden="true">
            V
          </span>
          <span>Voker</span>
        </NavLink>
      </SidebarHeader>

      <SidebarContent className="overflow-hidden">
        <SidebarGroup className="voker-sidebar-group">
          <SidebarGroupLabel className="voker-sidebar-label">
            Voice operations
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <nav aria-label="Dashboard">
              <SidebarMenu>
                {navigation.map(({ label, to, icon: Icon, end }) => {
                  const isActive = end
                    ? location.pathname === to
                    : location.pathname === to ||
                      location.pathname.startsWith(`${to}/`);

                  return (
                    <SidebarMenuItem key={to}>
                      <SidebarMenuButton
                        asChild
                        className="voker-sidebar-link"
                        isActive={isActive}
                        size="lg"
                        tooltip={label}
                      >
                        <NavLink
                          onClick={() => setOpenMobile(false)}
                          to={to}
                          end={end}
                        >
                          <Icon aria-hidden="true" />
                          <span>{label}</span>
                        </NavLink>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </nav>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="voker-sidebar-footer">
        <div className="account-menu">
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
            disabled={isSigningOut}
            onClick={onLogout}
          >
            {isSigningOut ? "Signing out…" : "Sign out"}
          </Button>
          {logoutFailed ? <small>Could not sign out. Try again.</small> : null}
        </div>
      </SidebarFooter>
    </Sidebar>
  );
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
    <SidebarProvider
      className="dashboard-sidebar-root"
      style={{ "--sidebar-width": "224px" } as CSSProperties}
    >
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <DashboardSidebar
        account={account}
        isSigningOut={logout.isPending}
        logoutFailed={logout.isError}
        onLogout={() => logout.mutate()}
      />
      <div className="dashboard-scroll-region">
        <header className="mobile-dashboard-nav">
          <NavLink className="mobile-brand" to="/">
            <span className="brand-mark" aria-hidden="true">
              V
            </span>
            <span>Voker</span>
          </NavLink>
          <SidebarTrigger
            aria-label="Open navigation menu"
            className="mobile-menu-trigger"
          />
        </header>
        <div id="main-content">
          <Outlet />
        </div>
      </div>
    </SidebarProvider>
  );
}
