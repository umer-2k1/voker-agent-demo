import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Bot,
  ChevronsUpDown,
  Headphones,
  LayoutDashboard,
  LogOut,
  PlugZap,
  Settings,
} from "lucide-react";

import type { Account } from "@/pages/AccountPage";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8001";

const navigation = [
  { label: "Overview", to: "/", icon: LayoutDashboard, end: true },
  { label: "Sessions", to: "/sessions", icon: Headphones, end: false },
  { label: "Setup", to: "/setup", icon: PlugZap, end: false },
  { label: "Agents", to: "/agents", icon: Bot, end: false },
  { label: "Workspace settings", to: "/settings", icon: Settings, end: false },
] as const;

const routeLabels: Array<[string, string]> = [
  ["/sessions", "Sessions"],
  ["/setup", "Setup"],
  ["/agents", "Agents"],
  ["/settings", "Workspace settings"],
];

function routeLabel(pathname: string) {
  return (
    routeLabels.find(([prefix]) => pathname.startsWith(prefix))?.[1] ??
    "Overview"
  );
}

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
      collapsible="icon"
      role="navigation"
    >
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild size="lg" tooltip="Voker">
              <NavLink
                aria-label="Voker overview"
                onClick={() => setOpenMobile(false)}
                to="/"
              >
                <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-sidebar-accent text-sm font-semibold text-sidebar-accent-foreground">
                  V
                </span>
                <span className="font-display text-base font-semibold tracking-tight">
                  Voker
                </span>
              </NavLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Voice operations</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu className="gap-2">
              {navigation.map(({ label, to, icon: Icon, end }) => {
                const isActive = end
                  ? location.pathname === to
                  : location.pathname === to ||
                    location.pathname.startsWith(`${to}/`);
                return (
                  <SidebarMenuItem key={to}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive}
                      tooltip={label}
                    >
                      <NavLink
                        end={end}
                        onClick={() => setOpenMobile(false)}
                        to={to}
                      >
                        <Icon aria-hidden="true" />
                        <span>{label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  aria-label="Account menu"
                  size="lg"
                  tooltip={account.display_name ?? account.email}
                >
                  <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-sidebar-accent text-xs font-semibold text-sidebar-accent-foreground">
                    {initials(account)}
                  </span>
                  <span className="grid flex-1 text-left text-sm leading-tight">
                    <span
                      className="truncate font-medium"
                      title={account.display_name ?? "Google account"}
                    >
                      {account.display_name ?? "Google account"}
                    </span>
                    <span
                      className="truncate text-xs text-sidebar-foreground/70"
                      title={account.email}
                    >
                      {account.email}
                    </span>
                  </span>
                  <ChevronsUpDown className="ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-60" side="right">
                <DropdownMenuLabel>
                  <span
                    className="block truncate text-sm font-medium"
                    title={account.display_name ?? "Google account"}
                  >
                    {account.display_name ?? "Google account"}
                  </span>
                  <span
                    className="block truncate text-xs font-normal text-muted-foreground"
                    title={account.email}
                  >
                    {account.email}
                  </span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  disabled={isSigningOut}
                  onClick={onLogout}
                >
                  <LogOut className="size-4" />
                  {isSigningOut ? "Signing out…" : "Sign out"}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            {logoutFailed ? (
              <p className="px-2 pt-1 text-xs text-destructive">
                Could not sign out. Try again.
              </p>
            ) : null}
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

export function AppShell({ account }: { account: Account }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const location = useLocation();
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
    <SidebarProvider className="dashboard-sidebar-root">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <DashboardSidebar
        account={account}
        isSigningOut={logout.isPending}
        logoutFailed={logout.isError}
        onLogout={() => logout.mutate()}
      />
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background/80 px-3 backdrop-blur sm:px-4">
          <SidebarTrigger aria-label="Toggle navigation" />
          <Separator className="mx-1 h-5" orientation="vertical" />
          <span className="hidden text-sm text-muted-foreground sm:inline">
            Voice operations
          </span>
          <span className="hidden text-muted-foreground sm:inline">/</span>
          <span
            className="truncate text-sm font-medium"
            title={routeLabel(location.pathname)}
          >
            {routeLabel(location.pathname)}
          </span>
        </header>
        <div className="min-w-0" id="main-content">
          <Outlet />
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
