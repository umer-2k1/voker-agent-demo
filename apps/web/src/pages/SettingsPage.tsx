import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001";
const projectSlug = import.meta.env.VITE_PROJECT_SLUG ?? "voker-voice";

type ApiKey = { id: string; label: string; prefix: string; environment: string; revoked_at: string | null };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { credentials: "include", ...init });
  if (!response.ok) throw new Error(response.status === 401 ? "Sign in required" : "Request failed");
  return response.json() as Promise<T>;
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState("");
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const keys = useQuery({ queryKey: ["api-keys", projectSlug], queryFn: () => request<{ items: ApiKey[] }>(`/api/projects/${projectSlug}/api-keys`) });
  const createKey = useMutation({
    mutationFn: () => request<{ api_key: string }>(`/api/projects/${projectSlug}/api-keys`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ label, environment: "development" }) }),
    onSuccess: (result) => { setRevealedKey(result.api_key); setLabel(""); void queryClient.invalidateQueries({ queryKey: ["api-keys", projectSlug] }); },
  });
  const revokeKey = useMutation({ mutationFn: (id: string) => request(`/api/projects/${projectSlug}/api-keys/${id}/revoke`, { method: "POST" }), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["api-keys", projectSlug] }) });
  return <main className="settings-page"><p className="eyebrow">Project settings</p><h1>API keys</h1><p className="settings-copy">Create scoped ingest keys for your voice agents. The secret is shown once only.</p>{revealedKey ? <pre className="revealed-key">Copy this key now: {revealedKey}</pre> : null}<form className="key-form" onSubmit={(event) => { event.preventDefault(); if (label.trim()) createKey.mutate(); }}><input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Key label" aria-label="Key label" /><button disabled={createKey.isPending}>Create key</button></form>{keys.isPending ? <div className="skeleton-list"><i /><i /><i /></div> : null}{keys.isError ? <p className="connection-error">{keys.error.message}. <a href={`${apiBaseUrl}/auth/google/login`}>Sign in with Google</a></p> : null}<div className="key-list">{keys.data?.items.map((key) => <div className="key-row" key={key.id}><span><b>{key.label}</b><small>{key.prefix} · {key.environment}</small></span>{key.revoked_at ? <em>Revoked</em> : <button onClick={() => revokeKey.mutate(key.id)}>Revoke</button>}</div>)}</div></main>;
}
