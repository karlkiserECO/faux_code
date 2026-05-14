import Sidebar from "@/components/Sidebar";
import ChatView from "@/components/ChatView";

export default async function ChatConvPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="flex">
      <Sidebar activeId={id} />
      <ChatView conversationId={id} />
    </div>
  );
}
