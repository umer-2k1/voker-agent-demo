import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import type { Account } from "@/pages/AccountPage";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8001";
const projectSlug = import.meta.env.VITE_PROJECT_SLUG ?? "voker-voice";
type ApiKey = {
  id: string;
  label: string;
  prefix: string;
  environment: string;
  revoked_at: string | null;
};
const createKeySchema = z.object({ label: z.string().trim().min(2, "Use at least 2 characters for the key label.") });

function initials(account: Account) {
  return (account.display_name?.trim() || account.email)
    .split(/\s+|@/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    credentials: "include",
    ...init,
  });
  if (!response.ok)
    throw new Error(
      response.status === 401 ? "Sign in required" : "Request failed",
    );
  return response.json() as Promise<T>;
}

export function SettingsPage({ account }: { account: Account }) {
  const queryClient = useQueryClient();
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const [revokeCandidate, setRevokeCandidate] = useState<ApiKey | null>(null);
  const form = useForm<z.infer<typeof createKeySchema>>({
    resolver: zodResolver(createKeySchema),
    defaultValues: { label: "" },
  });
  const keys = useQuery({
    queryKey: ["api-keys", projectSlug],
    queryFn: () =>
      request<{ items: ApiKey[] }>(`/api/projects/${projectSlug}/api-keys`),
  });
  const createKey = useMutation({
    mutationFn: (label: string) =>
      request<{ api_key: string }>(`/api/projects/${projectSlug}/api-keys`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ label, environment: "development" }),
      }),
    onSuccess: (result) => {
      setRevealedKey(result.api_key);
      form.reset();
      void queryClient.invalidateQueries({
        queryKey: ["api-keys", projectSlug],
      });
    },
  });
  const revokeKey = useMutation({
    mutationFn: (id: string) =>
      request(`/api/projects/${projectSlug}/api-keys/${id}/revoke`, {
        method: "POST",
      }),
    onSuccess: () => {
      setRevokeCandidate(null);
      return void queryClient.invalidateQueries({
        queryKey: ["api-keys", projectSlug],
      });
    },
  });
  return (
    <main className="mx-auto w-full max-w-7xl px-6 py-10 md:px-10 md:py-14">
      <header className="mb-8 flex flex-col gap-5 border-b border-[#dce8e5] pb-7 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[.14em] text-[#267469]">
            Workspace settings
          </p>
          <h1 className="mt-2 max-w-none text-4xl font-semibold tracking-[-.05em] text-[#173c36] md:text-5xl">
            Manage your workspace
          </h1>
          <p className="mt-3 max-w-2xl text-base leading-7 text-[#607a76]">
            Account identity and project ingest access, kept together in one
            place.
          </p>
        </div>
        <span className="inline-flex w-fit items-center gap-2 rounded-full border border-[#cce0db] bg-[#eaf5f3] px-3 py-2 text-xs font-bold text-[#176258]">
          <i className="h-2 w-2 rounded-full bg-[#20a28b]" />
          {projectSlug}
        </span>
      </header>
      <nav className="mb-6 !flex gap-6" aria-label="Settings sections">
        <a
          className="border-b-2 border-[#20a28b] pb-3 text-sm font-bold text-[#004d43]"
          href="#profile"
        >
          Profile
        </a>
        <a
          className="border-b-2 border-transparent pb-3 text-sm font-bold text-[#718882] hover:text-[#004d43]"
          href="#api-keys"
        >
          API keys
        </a>
      </nav>
      <div className="grid gap-5 lg:grid-cols-[minmax(300px,.82fr)_minmax(0,1.5fr)]">
        <section
          className="rounded-2xl border border-[#dce8e5] bg-white p-6 shadow-[0_2px_8px_rgb(15_38_34/3%)]"
          id="profile"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-[.14em] text-[#267469]">
                Profile
              </p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-.03em] text-[#173c36]">
                Signed-in account
              </h2>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full bg-[#eaf5f3] px-3 py-1.5 text-xs font-bold text-[#176258]">
              <i className="h-2 w-2 rounded-full bg-[#20a28b]" />
              Connected
            </span>
          </div>
          <div className="mt-7 flex items-center gap-4 rounded-xl border border-[#d8e8e4] bg-gradient-to-br from-[#f0f8f6] to-white p-5">
            <span className="grid h-14 w-14 shrink-0 place-items-center rounded-xl bg-[#004d43] text-lg font-extrabold text-white">
              {initials(account)}
            </span>
            <div className="min-w-0">
              <h3 className="truncate text-base font-bold text-[#254841]">
                {account.display_name ?? "Google account"}
              </h3>
              <p className="mt-1 truncate text-sm text-[#607a76]">
                {account.email}
              </p>
              <small className="mt-2 block text-xs font-bold text-[#267469]">
                Authenticated securely with Google
              </small>
            </div>
          </div>
          <div className="mt-6 border-t border-[#e7eeec] pt-5 text-sm leading-6 text-[#718882]">
            <b className="block text-[#254841]">
              Your identity is managed by Google.
            </b>
            <span>
              Use the profile control in the sidebar to sign out of this
              workspace.
            </span>
          </div>
        </section>
        <section
          className="rounded-2xl border border-[#dce8e5] bg-white p-6 shadow-[0_2px_8px_rgb(15_38_34/3%)]"
          id="api-keys"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs font-bold uppercase tracking-[.14em] text-[#267469]">
                Ingest access
              </p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-.03em] text-[#173c36]">
                Project API keys
              </h2>
              <p className="mt-2 max-w-lg text-sm leading-6 text-[#718882]">
                Create a scoped key for an agent. The complete secret is shown
                once.
              </p>
            </div>
            <span className="w-fit rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-[#607a76]">
              {keys.data?.items.length ?? 0} keys
            </span>
          </div>
          {revealedKey ? (
            <div className="mt-6 grid gap-2 rounded-xl border border-[#f0cc87] bg-[#fff7e9] p-4 text-sm">
              <b className="text-[#765515]">Copy this key now</b>
              <code className="break-all text-[#5e491f]">{revealedKey}</code>
            </div>
          ) : null}
          <Form {...form}>
          <form
            className="mt-7 flex flex-col gap-3 sm:flex-row sm:items-end"
            onSubmit={form.handleSubmit((values) => createKey.mutate(values.label))}
          >
            <FormField control={form.control} name="label" render={({ field }) => (
              <FormItem className="flex-1">
                <FormLabel>Key label</FormLabel>
                <FormControl><Input placeholder="e.g. Production voice agent" {...field} /></FormControl>
                <FormMessage />
              </FormItem>
            )} />
            <Button
              type="submit"
              disabled={createKey.isPending}
            >
              {createKey.isPending ? "Creating…" : "Create key"}
            </Button>
          </form>
          </Form>
          {keys.isPending ? (
            <div className="mt-5 space-y-2">
              <div className="h-15 animate-pulse rounded-lg bg-[#eaf5f3]" />
              <div className="h-15 animate-pulse rounded-lg bg-[#eaf5f3]" />
            </div>
          ) : null}
          {keys.isError ? (
            <p className="mt-5 rounded-lg border border-[#efc2bb] bg-[#fff4f2] p-4 text-sm text-[#9e3325]">
              {keys.error.message}.
            </p>
          ) : null}
          {revokeCandidate ? (
            <section
              aria-labelledby="revoke-title"
              className="mt-5 rounded-xl border border-[#efc2bb] bg-[#fff4f2] p-4 text-sm text-[#5e491f]"
            >
              <b className="block text-[#7b2d22]" id="revoke-title">
                Revoke {revokeCandidate.label}?
              </b>
              <p className="mt-2 leading-6">
                This immediately stops {revokeCandidate.environment} agents
                using this key. Create a replacement key before continuing.
              </p>
              {revokeKey.isError ? (
                <p className="mt-2 font-semibold text-[#9e3325]" role="alert">
                  Could not revoke this key. Please try again.
                </p>
              ) : null}
              <div className="mt-4 flex flex-wrap gap-3">
                <Button
                  variant="outline"
                  disabled={revokeKey.isPending}
                  onClick={() => setRevokeCandidate(null)}
                  type="button"
                >
                  Keep key
                </Button>
                <Button
                  variant="destructive"
                  disabled={revokeKey.isPending}
                  onClick={() => revokeKey.mutate(revokeCandidate.id)}
                  type="button"
                >
                  {revokeKey.isPending ? "Revoking…" : "Revoke key"}
                </Button>
              </div>
            </section>
          ) : null}
          <div className="mt-5 overflow-hidden rounded-xl border border-[#dce8e5]">
            {keys.data?.items.length ? (
              keys.data.items.map((key) => (
                <div
                  className="grid grid-cols-[30px_minmax(0,1fr)_auto] items-center gap-3 border-b border-[#e7eeec] p-4 last:border-0"
                  key={key.id}
                >
                  <span
                    aria-hidden="true"
                    className="grid h-8 w-8 place-items-center rounded-lg bg-[#eaf5f3] text-[#176258]"
                  >
                    <KeyRound size={15} strokeWidth={2} />
                  </span>
                  <span className="min-w-0">
                    <b className="block truncate text-sm text-[#254841]">
                      {key.label}
                    </b>
                    <small className="mt-1 block text-xs text-[#829a95]">
                      {key.prefix} · {key.environment}
                    </small>
                  </span>
                  {key.revoked_at ? (
                    <em className="text-xs not-italic text-[#829a95]">
                      Revoked
                    </em>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-destructive/30 text-destructive hover:bg-destructive/10"
                      type="button"
                      onClick={() => setRevokeCandidate(key)}
                    >
                      Revoke
                    </Button>
                  )}
                </div>
              ))
            ) : !keys.isPending ? (
              <div className="grid gap-1 px-6 py-9 text-center text-sm text-[#718882]">
                <b className="text-[#254841]">No API keys yet</b>
                <span>
                  Create a key above when you are ready to connect an agent.
                </span>
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </main>
  );
}
