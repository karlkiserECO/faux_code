import Sidebar from "@/components/Sidebar";
import AgentView from "@/components/AgentView";

export default function AgentPage() {
  return (
    <div className="flex">
      <Sidebar />
      <AgentView />
    </div>
  );
}
