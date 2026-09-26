export type WorkspaceProject = {
  id: string;
  name: string;
  slug: string;
};

export function resolveProjectSlug(
  projects: WorkspaceProject[],
  preferredSlug: string,
) {
  return (
    projects.find((project) => project.slug === preferredSlug)?.slug ??
    projects[0]?.slug ??
    ""
  );
}

export async function loadProjects(apiBaseUrl: string) {
  const response = await fetch(`${apiBaseUrl}/api/projects`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(
      response.status === 401 ? "Sign in required" : "Unable to load projects.",
    );
  }
  return response.json() as Promise<{ items: WorkspaceProject[] }>;
}
