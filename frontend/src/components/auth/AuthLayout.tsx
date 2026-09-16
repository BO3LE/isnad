import type { ReactNode } from "react";
import { Logo } from "@/components/app/Logo";
import { ChainRule } from "@/design-system/patterns/ChainRule";
import { HandoffLines } from "@/design-system/patterns/HandoffLines";

// S-01 (DESIGN-SYSTEM.md §21) — shared by P-01 Sign in and P-02 Create account.
// Two columns at lg and up (form 40%, hero 60%); one column below, with the gradient reduced to a
// 160 px header strip so the form is still the first thing on a phone.
export function AuthLayout({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="grid min-h-full lg:grid-cols-[40fr_60fr]">
      {/* Mobile: the hero becomes a strip above the form. */}
      <div className="gradient-handoff grain relative h-40 overflow-hidden lg:hidden">
        <HandoffLines className="absolute inset-x-0 bottom-0 h-28 w-full text-[#9fb6ff] opacity-40" />
      </div>

      <main className="flex items-center justify-center px-6 py-10 md:px-10">
        <div className="grid w-full max-w-[480px] gap-8">
          <Logo className="text-text" />

          <div className="grid gap-1.5">
            <h1 className="text-heading-xl text-text">{title}</h1>
            <p className="text-body-md text-text-muted">{subtitle}</p>
          </div>

          {children}

          <div className="grid justify-items-start gap-4 border-t border-border pt-6">
            <ChainRule className="h-3 w-40 text-border-strong" />
            <p className="text-caption text-text-muted">King Faisal University · CCSIT · Graduation Project 2026</p>
          </div>
        </div>
      </main>

      {/* Hero: lg and up only. Decorative, so it is hidden from screen readers entirely — the
          headline repeats the marketing line and carries no information the form needs. */}
      <aside aria-hidden className="gradient-handoff grain relative hidden overflow-hidden lg:block">
        <HandoffLines lines={40} className="absolute inset-0 h-full w-full text-[#9fb6ff] opacity-35" />
        <div className="relative flex h-full flex-col justify-between p-12 xl:p-16">
          <Logo className="text-[#fafaf8]" />
          {/* ch is relative to each element's own font-size, so the measure lives on the text, not
              on the wrapper — on the wrapper it would resolve against 14 px and wrap far too early.
              The headline breaks at the comma, as S-01 and the landing page both set it. */}
          <div className="grid gap-6">
            <p className="font-serif text-display-lg text-[#fafaf8]">
              Your pipeline,
              <br />
              one canvas.
            </p>
            <p className="max-w-[38ch] text-body-lg text-[#d5ddf7]">
              Research, write, produce, publish and email — from one chain of agents you can watch.
            </p>
          </div>
          <ChainRule links={5} className="h-3 w-56 text-[#9fb6ff]" />
        </div>
      </aside>
    </div>
  );
}
