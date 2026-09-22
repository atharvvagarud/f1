// Shared application shell (UI1). Every implemented route renders inside this
// one frame so the product reads as a single race-intelligence workstation.
// Server component: route awareness is isolated in CommandBar.

import { CommandBar } from "@/components/shell/CommandBar";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-ink-950 text-fg">
      <CommandBar />
      <main className="flex-1">{children}</main>
    </div>
  );
}
