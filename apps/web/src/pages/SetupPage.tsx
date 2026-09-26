import { useState, type ReactNode } from "react";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingState } from "@/components/ui/loading";
import { NativeSelect } from "@/components/ui/native-select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Eyebrow,
  H1,
  H2,
  Lead,
  Muted,
  Small,
  Text,
} from "@/components/ui/typography";

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

const PROVIDER_LABELS: Record<string, string> = {
  sdk: "Generic Python SDK",
  livekit: "LiveKit",
  langgraph: "LangGraph",
  vapi: "Vapi",
  retell: "Retell",
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

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <div className="mt-1">{children}</div>
    </div>
  );
}

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
  const noun = provider === "vapi" ? "assistants" : "agents";
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
    <div className="mt-5 flex flex-col gap-4 rounded-xl border border-border bg-muted/40 p-4">
      {current ? (
        <div className="grid gap-4 rounded-lg border border-border bg-card p-4 sm:grid-cols-2">
          <Field label="Connection">
            <Text className="font-semibold capitalize">
              {current.status.replaceAll("_", " ")}
            </Text>
          </Field>
          <Field label="Last delivery">
            <Text className="text-muted-foreground">
              {current.last_delivery_at
                ? new Intl.DateTimeFormat(undefined, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(current.last_delivery_at))
                : "Not yet observed"}
              {` · ${current.normalization_state.replaceAll("_", " ")}`}
            </Text>
          </Field>
          <Field label={`Selected ${noun}`}>
            <Text className="text-muted-foreground">
              {current.selected_resources.length
                ? current.selected_resources.map((item) => item.name).join(", ")
                : "None selected"}
            </Text>
          </Field>
          {current.forwarding_destinations.length ? (
            <Field label="Existing webhook forwarding">
              <Text className="break-all text-muted-foreground">
                {current.forwarding_enabled ? "Enabled" : "Disabled"} ·{" "}
                {current.forwarding_failures} pending/failed ·{" "}
                {current.forwarding_destinations.join(", ")}
              </Text>
            </Field>
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
                Load {noun}
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
            <Small>
              Sent only to the Voker API, validated with{" "}
              {provider === "vapi" ? "Vapi" : "Retell"}, then stored encrypted.
            </Small>
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
            <legend className="text-sm font-semibold text-foreground">
              Select {noun}
            </legend>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {resources.map((resource) => (
                <label
                  className="flex cursor-pointer gap-3 rounded-lg border border-border bg-card p-3 text-sm transition-colors hover:bg-accent/50"
                  key={resource.id}
                >
                  <input
                    className="mt-0.5 size-4 accent-primary"
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
                    <b className="block font-medium text-foreground">
                      {resource.name}
                    </b>
                    <Small>
                      {resource.version
                        ? `Version ${resource.version}`
                        : "Version unknown"}
                      {resource.existing_webhook_url
                        ? " · existing webhook preserved"
                        : ""}
                    </Small>
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
            <Small>
              The provider must be able to reach this URL. Existing webhook
              destinations are forwarded automatically.
            </Small>
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
        <LoadingState label="Loading provider resources…" className="py-6" />
      ) : null}
      {error ? (
        <p className="text-sm text-destructive" role="alert">
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
    "";
  const setup = useQuery({
    queryKey: ["project-setup", selectedProject],
    queryFn: () =>
      request<ProjectSetup>(`/api/projects/${selectedProject}/setup`),
    enabled: Boolean(selectedProject),
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
  const observedStages = setup.data?.observed_stages ?? [];
  const loadingSetup = projects.isPending || (setup.isPending && !setup.data);

  return (
    <main className="mx-auto w-full max-w-7xl px-6 py-8 md:px-10 md:py-10">
      <header className="mb-6 flex flex-col gap-4 border-b border-border pb-5 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <Eyebrow>Setup</Eyebrow>
          <H1 className="mt-2 max-w-3xl">
            Connect a voice pipeline and verify what Voker observes.
          </H1>
          <Lead className="mt-2 max-w-2xl">
            Choose the integration boundary you own. Provider data that has not
            arrived is shown as unknown, never as a failure.
          </Lead>
        </div>
        <div className="grid min-w-64 gap-3 sm:grid-cols-2">
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">
              Project
            </span>
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
          </label>
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">
              Environment
            </span>
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
          </label>
        </div>
      </header>

      {setup.isError ? (
        <p className="connection-error" role="alert">
          {setup.error.message}. Refresh to try again.
        </p>
      ) : null}

      {loadingSetup ? (
        <LoadingState label="Loading setup state…" className="py-16" />
      ) : (
        <section
          className="mb-6 grid gap-4 sm:grid-cols-3"
          aria-label="Integration observation state"
        >
          <Card className="shadow-none">
            <CardContent className="p-4">
              <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                <RadioTower className="size-4" /> Last event
              </span>
              <Text className="mt-2 font-semibold">
                {setup.data?.last_received_event_at
                  ? new Intl.DateTimeFormat(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(setup.data.last_received_event_at))
                  : "Not yet observed"}
              </Text>
            </CardContent>
          </Card>
          <Card className="shadow-none sm:col-span-2">
            <CardContent className="p-4">
              <span className="text-xs font-medium text-muted-foreground">
                Observed pipeline stages
              </span>
              <div className="mt-2 flex flex-wrap gap-2">
                {observedStages.length ? (
                  observedStages.map((stage) => (
                    <Badge variant="success" key={stage}>
                      <CheckCircle2 className="size-3" /> {stage.toUpperCase()}
                    </Badge>
                  ))
                ) : (
                  <Text className="inline-flex items-center gap-2 text-muted-foreground">
                    <CircleDashed className="size-4" /> Waiting for the first
                    event; no integration failure has been detected.
                  </Text>
                )}
              </div>
            </CardContent>
          </Card>
        </section>
      )}

      <Tabs
        value={path}
        onValueChange={(value) => {
          setPath(value);
          setCopied(false);
        }}
        className="gap-4"
      >
        <TabsList
          className="h-auto w-full flex-wrap justify-start gap-1"
          variant="line"
        >
          {Object.keys(installCommands).map((value) => (
            <TabsTrigger value={value} key={value}>
              {PROVIDER_LABELS[value] ?? value}
            </TabsTrigger>
          ))}
        </TabsList>
        {Object.keys(installCommands).map((kind) => (
          <TabsContent
            value={kind}
            className="mt-2 grid gap-5 rounded-xl border border-border bg-card p-5 lg:grid-cols-[minmax(0,.8fr)_minmax(0,1.2fr)]"
            key={kind}
          >
            <div className="min-w-0">
              <H2>{PROVIDER_LABELS[kind] ?? kind}</H2>
              <Muted className="mt-2 max-w-xl">
                {installCommands[kind]}
              </Muted>
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
                <span className="text-xs font-medium text-muted-foreground">
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
                className="max-h-96 overflow-auto rounded-lg bg-foreground p-4 text-xs leading-6 whitespace-pre-wrap text-background"
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
