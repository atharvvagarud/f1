import { PitWallView } from "@/features/pit-wall/components/PitWallView";

export const metadata = {
  title: "Pit Wall | F1 Intelligence",
  description:
    "Integrated historical race-intelligence workspace: one canonical race state across track replay, selected driver, running order, and timeline.",
};

export default function PitWallPage() {
  return <PitWallView />;
}
