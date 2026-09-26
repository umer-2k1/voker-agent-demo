import { useEffect } from "react";

const SUFFIX = "Voker Voice";

/**
 * Set the document title for the current page. Restores the previous title on
 * unmount so nested/route transitions do not leak a stale heading.
 */
export function useDocumentTitle(title?: string) {
  useEffect(() => {
    const previous = document.title;
    document.title = title ? `${title} · ${SUFFIX}` : SUFFIX;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
