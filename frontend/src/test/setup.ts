import "@testing-library/jest-dom/vitest";

// jsdom does not implement <dialog>: showModal and close simply do not exist, so any test that
// renders the Dialog component throws "showModal is not a function". Dialog is built on the native
// element on purpose (§14.12 — focus trapping, Esc and inert background for free), so the gap is
// jsdom's rather than ours. Minimal stand-in, here rather than repeated in every test file.
if (typeof HTMLDialogElement !== "undefined" && !HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.show = function show(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement, returnValue?: string) {
    if (!this.open) return;
    this.open = false;
    if (returnValue !== undefined) this.returnValue = returnValue;
    this.dispatchEvent(new Event("close"));
  };
}

// jsdom also ships no user-agent stylesheet for <dialog>, so an open dialog computes to no display
// value at all. user-event's visibility check then refuses to click anything inside it — silently,
// which looks exactly like a component bug. These are the two UA rules a real browser applies.
const dialogUserAgentStyles = document.createElement("style");
dialogUserAgentStyles.textContent = "dialog[open]{display:block}dialog:not([open]){display:none}";
document.head.appendChild(dialogUserAgentStyles);
