import { ReplayView } from "@/features/replay/components/ReplayView";

export const metadata = {
  title: "Historical Race Replay | F1 Intelligence",
  description:
    "Step through served 2018–2024 races frame by frame with factual race states and cached winner checkpoints.",
};

export default function ReplayPage() {
  return <ReplayView />;
}
