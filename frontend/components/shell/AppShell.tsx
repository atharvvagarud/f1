// Shared application shell (UI1). Every implemented route renders inside this
// one frame so the product reads as a single race-intelligence workstation.
// Server component: route awareness is isolated in CommandBar.

import { CommandBar } from "@/components/shell/CommandBar";
import { WorkspaceProvider } from "@/features/workspace/hooks/useWorkspace";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-ink-950 text-fg">
      <WorkspaceProvider>
        <CommandBar />
        <main className="flex-1">{children}</main>
      </WorkspaceProvider>
    </div>
  );
}
