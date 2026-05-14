import Sidebar from "@/components/Sidebar";
import ChatView from "@/components/ChatView";

export default function ChatHomePage() {
  return (
    <div className="flex">
      <Sidebar />
      <ChatView />
    </div>
  );
}
