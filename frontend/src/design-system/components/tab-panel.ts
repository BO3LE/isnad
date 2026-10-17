// The panel half of §14.9's tab pattern. Its own module because a file that exports both a
// component and a plain function loses fast refresh, and `Tabs` is edited often enough to care.

export const slug = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

/**
 * The attributes a tab's panel needs, matching what `Tabs` puts on the tab itself.
 *
 * Spread onto the element holding the selected tab's content:
 * `<div {...tabPanel("Step panels", tab)}>`. A tab that controls nothing is only half a tab — a
 * screen reader announces "tab, 1 of 2" and then has no way to reach what it selected.
 *
 * The first argument is the tablist's `label`, or its `idPrefix` when one was given.
 */
export function tabPanel(labelOrPrefix: string, tabId: string) {
  const prefix = slug(labelOrPrefix);
  return {
    id: `${prefix}-panel-${tabId}`,
    role: "tabpanel" as const,
    "aria-labelledby": `${prefix}-tab-${tabId}`,
    tabIndex: 0,
  };
}
