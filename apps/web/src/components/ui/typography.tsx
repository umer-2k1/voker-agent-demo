import type { ComponentProps, ElementType } from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * Shared typography scale. Every text style in the app should come from one of
 * these variants so hierarchy, colour, and rhythm stay consistent. Fonts are
 * resolved from the `--font-*` tokens defined in styles.css.
 */
export const typographyVariants = cva("", {
  variants: {
    variant: {
      display:
        "font-display text-4xl font-semibold leading-[1.1] tracking-tight text-foreground sm:text-5xl",
      h1: "font-display text-3xl font-semibold leading-tight tracking-tight text-foreground",
      h2: "font-display text-2xl font-semibold leading-snug tracking-tight text-foreground",
      h3: "text-lg font-semibold leading-snug tracking-tight text-foreground",
      h4: "text-base font-semibold leading-snug text-foreground",
      lead: "text-lg leading-relaxed text-muted-foreground",
      body: "text-sm leading-relaxed text-foreground",
      muted: "text-sm leading-relaxed text-muted-foreground",
      small: "text-xs leading-normal text-muted-foreground",
      eyebrow:
        "font-display text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground",
      label: "text-xs font-medium text-muted-foreground",
      code: "font-mono text-xs text-foreground",
    },
  },
  defaultVariants: { variant: "body" },
});

export type TypographyVariant = NonNullable<
  VariantProps<typeof typographyVariants>["variant"]
>;

const defaultElement: Record<TypographyVariant, ElementType> = {
  display: "h1",
  h1: "h1",
  h2: "h2",
  h3: "h3",
  h4: "h4",
  lead: "p",
  body: "p",
  muted: "p",
  small: "p",
  eyebrow: "p",
  label: "span",
  code: "code",
};

export type TypographyProps = ComponentProps<"p"> & {
  as?: ElementType;
  variant?: TypographyVariant;
};

export function Typography({
  as,
  variant = "body",
  className,
  ...props
}: TypographyProps) {
  const Component = (as ?? defaultElement[variant]) as ElementType;
  return (
    <Component className={cn(typographyVariants({ variant }), className)} {...props} />
  );
}

/** Display — the single largest headline on a page. */
export const Display = (props: TypographyProps) => (
  <Typography variant="display" {...props} />
);
/** H1 — primary page title. */
export const H1 = (props: TypographyProps) => (
  <Typography variant="h1" {...props} />
);
/** H2 — panel or section title. */
export const H2 = (props: TypographyProps) => (
  <Typography variant="h2" {...props} />
);
/** H3 — card title. */
export const H3 = (props: TypographyProps) => (
  <Typography variant="h3" {...props} />
);
/** H4 — tightest heading, used inside dense cards. */
export const H4 = (props: TypographyProps) => (
  <Typography variant="h4" {...props} />
);
/** Lead — introductory paragraph under a headline. */
export const Lead = (props: TypographyProps) => (
  <Typography variant="lead" {...props} />
);
/** Text — default body copy. */
export const Text = (props: TypographyProps) => (
  <Typography variant="body" {...props} />
);
/** Muted — secondary body copy. */
export const Muted = (props: TypographyProps) => (
  <Typography variant="muted" {...props} />
);
/** Small — captions and metadata. */
export const Small = (props: TypographyProps) => (
  <Typography variant="small" {...props} />
);
/** Eyebrow — small uppercase label above a headline. */
export const Eyebrow = (props: TypographyProps) => (
  <Typography variant="eyebrow" {...props} />
);
/** Label — form and field labels. */
export const Label = (props: TypographyProps) => (
  <Typography variant="label" {...props} />
);
/** Code — inline or block monospace text. */
export const Code = (props: TypographyProps) => (
  <Typography variant="code" {...props} />
);
