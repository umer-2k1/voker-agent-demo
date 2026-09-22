import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  CircleDashed,
  Copy,
  LoaderCircle,
  RadioTower,
} from "lucide-react";

import type {
  ProjectSetup,
  ProviderResource,
} from "@/components/dashboard/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8001";
const defaultProjectSlug = import.meta.env.VITE_PROJECT_SLUG ?? "voker-voice";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    credentials: "include",
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });
  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(error?.detail ?? "Setup request failed");
  }
  return response.json() as Promise<T>;
}

const installCommands: Record<string, string> = {
  sdk: "pip install voker-voice",
  livekit: "pip install 'voker-voice[livekit]'",
  langgraph: "pip install 'voker-voice[langgraph]'",
  vapi: "Connect a Vapi credential and select an assistant below.",
  retell: "Connect a Retell credential and select an agent below.",
};

function snippet(kind: string, environment: string) {
  if (kind === "livekit")
    return `import os\nfrom voker_voice import VokerVoice, observe_livekit\n\nvoker = VokerVoice(api_key=os.environ["VOKER_API_KEY"])\nobserver = observe_livekit(agent_session, context=ctx, agent="support-agent", version="1.0", client=voker)`;
  if (kind === "langgraph")
    return `import os\nfrom voker_voice import VokerVoice, observe_langgraph\n\nvoker = VokerVoice(api_key=os.environ["VOKER_API_KEY"])\nasync with voker.session(agent="support-agent", version="1.0", session_id=call_id) as call:\n    result = await observe_langgraph(graph, session=call).ainvoke(inputs)`;
  if (kind === "sdk")
    return `import os\nfrom voker_voice import VokerVoice\n\nvoker = VokerVoice(api_key=os.environ["VOKER_API_KEY"])\nasync with voker.session(agent="support-agent", version="1.0", session_id=call_id) as call:\n    async with call.span("llm", provider="openrouter"):\n        ...`;
  return `Provider: ${kind}\nEnvironment: ${environment}\nContinue in the managed connector form.`;
}

type ConnectorProvider = "vapi" | "retell";

function ConnectorSetup({
  provider,
  projectSlug,
  environment,
  setup,
}: {
  provider: ConnectorProvider;
  projectSlug: string;
  environment: string;
  setup?: ProjectSetup;
}) {
  const queryClient = useQueryClient();
  const current = setup?.integrations.find(
    (item) => item.provider === provider,
  );
  const [apiKey, setApiKey] = useState("");
  const [publicBaseUrl, setPublicBaseUrl] = useState(apiBaseUrl);
  const [integrationId, setIntegrationId] = useState(current?.id ?? "");
  const [resources, setResources] = useState<ProviderResource[]>(
    current?.selected_resources ?? [],
  );
  const [selectedIds, setSelectedIds] = useState<string[]>(
    current?.selected_resources.map((item) => item.id) ?? [],
  );

  const refreshSetup = () =>
    queryClient.invalidateQueries({
      queryKey: ["project-setup", projectSlug],
    });

  const connect = useMutation({
    mutationFn: () =>
      request<{
        id: string;
        resources: ProviderResource[];
        status: string;
      }>(`/api/projects/${projectSlug}/integrations`, {
        method: "POST",
        body: JSON.stringify({
          provider,
          name: `${provider === "vapi" ? "Vapi" : "Retell"} managed connection`,
          api_key: apiKey,
        }),
      }),
    onSuccess: (result) => {
      setIntegrationId(result.id);
      setResources(result.resources);
      setSelectedIds([]);
      setApiKey("");
      void refreshSetup();
    },
  });

  const loadResources = useMutation({
    mutationFn: () =>
      request<{ items: ProviderResource[] }>(
        `/api/projects/${projectSlug}/integrations/${current?.id}/resources`,
      ),
    onSuccess: (result) => {
      setIntegrationId(current?.id ?? "");
      setResources(result.items);
    },
  });

  const configure = useMutation({
    mutationFn: () =>
      request(
        `/api/projects/${projectSlug}/integrations/${integrationId}/configure`,
        {
          method: "POST",
          body: JSON.stringify({
            selected_ids: selectedIds,
            public_base_url: publicBaseUrl,
            environment,
            forwarding_enabled: true,
          }),
        },
      ),
    onSuccess: () => {
      setResources([]);
      void refreshSetup();
    },
  });

  const update = useMutation({
    mutationFn: (values: { enabled?: boolean; forwarding_enabled?: boolean }) =>
      request(`/api/projects/${projectSlug}/integrations/${current?.id}`, {
        method: "PATCH",
        body: JSON.stringify(values),
      }),
    onSuccess: () => void refreshSetup(),
  });

  const pending =
    connect.isPending || configure.isPending || loadResources.isPending;
  const error =
    connect.error ?? configure.error ?? loadResources.error ?? update.error;

  return (
    <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50/70 p-4">
      {current ? (
        <div className="mb-4 grid gap-3 rounded-lg border border-slate-200 bg-white p-4 text-sm sm:grid-cols-2">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Connection
            </span>
            <p className="mt-1 font-semibold text-slate-900">
              {current.status.replaceAll("_", " ")}
            </p>
          </div>
          <div>
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Last delivery
            </span>
            <p className="mt-1 text-slate-700">
              {current.last_delivery_at
                ? new Intl.DateTimeFormat(undefined, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(current.last_delivery_at))
                : "Not yet observed"}
              {` · ${current.normalization_state.replaceAll("_", " ")}`}
            </p>
          </div>
          <div className="sm:col-span-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Selected {provider === "vapi" ? "assistants" : "agents"}
            </span>
            <p className="mt-1 text-slate-700">
              {current.selected_resources.length
                ? current.selected_resources.map((item) => item.name).join(", ")
                : "None selected"}
            </p>
          </div>
          {current.forwarding_destinations.length ? (
            <div className="sm:col-span-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Existing webhook forwarding
              </span>
              <p className="mt-1 break-all text-slate-700">
                {current.forwarding_enabled ? "Enabled" : "Disabled"} ·{" "}
                {current.forwarding_failures} pending/failed ·{" "}
                {current.forwarding_destinations.join(", ")}
              </p>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            {current.status === "active" ? (
              <Button
                size="sm"
                variant="outline"
                disabled={update.isPending}
                onClick={() => update.mutate({ enabled: false })}
              >
                Disable connection
              </Button>
            ) : current.status === "disabled" ? (
              <Button
                size="sm"
                variant="outline"
                disabled={update.isPending}
                onClick={() => update.mutate({ enabled: true })}
              >
                Enable connection
              </Button>
            ) : null}
            {current.status === "pending_configuration" && !resources.length ? (
              <Button
                size="sm"
                variant="outline"
                disabled={loadResources.isPending}
                onClick={() => loadResources.mutate()}
              >
                Load {provider === "vapi" ? "assistants" : "agents"}
              </Button>
            ) : null}
            {current.forwarding_destinations.length ? (
              <Button
                size="sm"
                variant="ghost"
                disabled={update.isPending}
                onClick={() =>
                  update.mutate({
                    forwarding_enabled: !current.forwarding_enabled,
                  })
                }
              >
                {current.forwarding_enabled ? "Pause" : "Resume"} forwarding
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      {!current && !integrationId ? (
        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <div className="grid gap-2">
            <Label htmlFor={`${provider}-key`}>Private API key</Label>
            <Input
              id={`${provider}-key`}
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={
                provider === "vapi" ? "Vapi private key" : "Retell API key"
              }
            />
            <p className="text-xs leading-5 text-slate-500">
              Sent only to the Voker API, validated with{" "}
              {provider === "vapi" ? "Vapi" : "Retell"}, then stored encrypted.
            </p>
          </div>
          <Button
            disabled={!apiKey || connect.isPending}
            onClick={() => connect.mutate()}
          >
            {connect.isPending ? (
              <LoaderCircle className="animate-spin" />
            ) : null}
            Validate and continue
          </Button>
        </div>
      ) : null}

      {resources.length ? (
        <div className="grid gap-4">
          <fieldset>
            <legend className="text-sm font-semibold text-slate-900">
              Select {provider === "vapi" ? "assistants" : "agents"}
            </legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {resources.map((resource) => (
                <label
                  className="flex cursor-pointer gap-3 rounded-lg border border-slate-200 bg-white p-3 text-sm"
                  key={resource.id}
                >
                  <input
                    className="mt-0.5 size-4 accent-emerald-700"
                    type="checkbox"
                    checked={selectedIds.includes(resource.id)}
                    onChange={(event) =>
                      setSelectedIds((items) =>
                        event.target.checked
                          ? [...items, resource.id]
                          : items.filter((item) => item !== resource.id),
                      )
                    }
                  />
                  <span>
                    <b className="block text-slate-900">{resource.name}</b>
                    <span className="text-xs text-slate-500">
                      {resource.version
                        ? `Version ${resource.version}`
                        : "Version unknown"}
                      {resource.existing_webhook_url
                        ? " · existing webhook preserved"
                        : ""}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="grid gap-2">
            <Label htmlFor={`${provider}-public-url`}>
              Public Voker API URL
            </Label>
            <Input
              id={`${provider}-public-url`}
              type="url"
              value={publicBaseUrl}
              onChange={(event) => setPublicBaseUrl(event.target.value)}
              placeholder="https://voice.example.com"
            />
            <p className="text-xs text-slate-500">
              The provider must be able to reach this URL. Existing webhook
              destinations are forwarded automatically.
            </p>
          </div>
          <Button
            className="w-fit"
            disabled={
              !selectedIds.length || !publicBaseUrl || configure.isPending
            }
            onClick={() => configure.mutate()}
          >
            {configure.isPending ? (
              <LoaderCircle className="animate-spin" />
            ) : null}
            Configure webhook
          </Button>
        </div>
      ) : null}

      {pending && !connect.isPending && !configure.isPending ? (
        <p className="mt-3 text-sm text-slate-600">
          Loading provider resources…
        </p>
      ) : null}
      {error ? (
        <p className="mt-3 text-sm text-red-700" role="alert">
          {error.message}
        </p>
      ) : null}
    </div>
  );
}

export function SetupPage() {
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () =>
      request<{ items: Array<{ id: string; name: string; slug: string }> }>(
        "/api/projects",
      ),
  });
  const [projectChoice, setProjectChoice] = useState(defaultProjectSlug);
  const projectItems = projects.data?.items ?? [];
  const selectedProject =
    projectItems.find((item) => item.slug === projectChoice)?.slug ??
    projectItems[0]?.slug ??
    projectChoice;
  const setup = useQuery({
    queryKey: ["project-setup", selectedProject],
    queryFn: () =>
      request<ProjectSetup>(`/api/projects/${selectedProject}/setup`),
  });
  const [environmentChoice, setEnvironmentChoice] = useState("development");
  const environmentItems = setup.data?.environments ?? [];
  const environment =
    environmentItems.find((item) => item.slug === environmentChoice)?.slug ??
    environmentItems[0]?.slug ??
    environmentChoice;
  const [path, setPath] = useState("sdk");
  const [copied, setCopied] = useState(false);
  const code = snippet(path, environment);

  return (
    <main className="mx-auto w-full max-w-7xl px-6 py-10 md:px-10 md:py-14">
      <header className="mb-8 flex flex-col gap-5 border-b border-emerald-950/10 pb-7 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="max-w-3xl text-4xl font-semibold tracking-[-.04em] text-[#173c36]">
            Connect a voice pipeline and verify what Voker observes.
          </h1>
          <p className="mt-3 max-w-2xl text-base leading-7 text-[#506a65]">
            Choose the integration boundary you own. Provider data that has not
            arrived is shown as unknown, never as a failure.
          </p>
        </div>
        <div className="grid min-w-64 gap-2 sm:grid-cols-2">
          <NativeSelect
            aria-label="Project"
            value={selectedProject}
            onChange={(event) => setProjectChoice(event.target.value)}
          >
            {projectItems.map((project) => (
              <option key={project.id} value={project.slug}>
                {project.name}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect
            aria-label="Environment"
            value={environment}
            onChange={(event) => setEnvironmentChoice(event.target.value)}
          >
            {environmentItems.map((item) => (
              <option key={item.id} value={item.slug}>
                {item.name}
              </option>
            ))}
          </NativeSelect>
        </div>
      </header>

      {setup.isError ? (
        <p className="connection-error" role="alert">
          {setup.error.message}. Refresh to try again.
        </p>
      ) : null}
      <section
        className="mb-6 grid gap-px overflow-hidden rounded-xl border border-slate-200 bg-slate-200 sm:grid-cols-3"
        aria-label="Integration observation state"
      >
        <div className="bg-white p-5">
          <span className="flex items-center gap-2 text-xs font-semibold text-slate-500">
            <RadioTower size={15} /> Last event
          </span>
          <b className="mt-2 block text-sm text-slate-800">
            {setup.data?.last_received_event_at
              ? new Intl.DateTimeFormat(undefined, {
                  dateStyle: "medium",
                  timeStyle: "short",
                }).format(new Date(setup.data.last_received_event_at))
              : "Not yet observed"}
          </b>
        </div>
        <div className="bg-white p-5 sm:col-span-2">
          <span className="text-xs font-semibold text-slate-500">
            Observed pipeline stages
          </span>
          <div className="mt-2 flex flex-wrap gap-2">
            {setup.data?.observed_stages.length ? (
              setup.data.observed_stages.map((stage) => (
                <span
                  className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-800"
                  key={stage}
                >
                  <CheckCircle2 size={13} /> {stage.toUpperCase()}
                </span>
              ))
            ) : (
              <span className="inline-flex items-center gap-2 text-sm text-slate-600">
                <CircleDashed size={15} /> Waiting for the first event; no
                integration failure has been detected.
              </span>
            )}
          </div>
        </div>
      </section>

      <Tabs
        value={path}
        onValueChange={(value) => {
          setPath(value);
          setCopied(false);
        }}
        className="rounded-xl border border-slate-200 bg-white p-5"
      >
        <TabsList
          className="h-auto w-full flex-wrap justify-start"
          variant="line"
        >
          {[
            ["sdk", "Python SDK"],
            ["livekit", "LiveKit"],
            ["langgraph", "LangGraph"],
            ["vapi", "Vapi"],
            ["retell", "Retell"],
          ].map(([value, label]) => (
            <TabsTrigger value={value} key={value}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
        {Object.keys(installCommands).map((kind) => (
          <TabsContent
            value={kind}
            className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,.7fr)_minmax(0,1.3fr)]"
            key={kind}
          >
            <div>
              <h2 className="text-xl font-semibold text-slate-900">
                {kind === "sdk"
                  ? "Generic Python SDK"
                  : kind[0].toUpperCase() + kind.slice(1)}
              </h2>
              <p className="mt-2 max-w-xl text-sm leading-6 text-slate-600">
                {installCommands[kind]}
              </p>
              {kind === "vapi" || kind === "retell" ? (
                <ConnectorSetup
                  key={`${selectedProject}-${kind}`}
                  provider={kind}
                  projectSlug={selectedProject}
                  environment={environment}
                  setup={setup.data}
                />
              ) : null}
            </div>
            <div className="min-w-0">
              <div className="mb-2 flex items-center justify-between gap-3">
                <span className="text-xs font-semibold text-slate-500">
                  {environment} configuration
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    void navigator.clipboard?.writeText(code);
                    setCopied(true);
                    window.setTimeout(() => setCopied(false), 1800);
                  }}
                >
                  <Copy size={13} /> {copied ? "Copied" : "Copy"}
                </Button>
              </div>
              <pre
                tabIndex={0}
                className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950 p-4 text-xs leading-6 text-slate-100"
              >
                {code}
              </pre>
            </div>
          </TabsContent>
        ))}
      </Tabs>
    </main>
  );
}
