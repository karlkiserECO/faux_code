"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ConversationSummary,
  deleteConversation,
  listConversations,
} from "@/lib/api";
import { Plus, MessageSquare, Trash2, Settings, Code2, FileText, Wrench } from "lucide-react";
import clsx from "clsx";

export default function Sidebar({ activeId }: { activeId?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    try {
      const data = await listConversations();
      setItems(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, []);

  async function onDelete(id: string) {
    if (!confirm("Delete this conversation?")) return;
    await deleteConversation(id);
    await refresh();
    if (activeId === id) router.push("/chat");
  }

  return (
    <aside className="w-72 shrink-0 border-r border-border bg-card flex flex-col h-screen">
      <div className="p-3 flex flex-col gap-1">
        <div className="flex items-center justify-between px-2 py-2">
          <Link href="/chat" className="font-semibold text-base tracking-tight">
            faux<span className="text-accent">_</span>code
          </Link>
        </div>
        <Link
          href="/chat"
          className="flex items-center gap-2 px-3 py-2 rounded-md hover:bg-background border border-border"
        >
          <Plus size={16} /> New chat
        </Link>
        <Link
          href="/agent"
          className={clsx(
            "flex items-center gap-2 px-3 py-2 rounded-md hover:bg-background",
            pathname?.startsWith("/agent") && "bg-background"
          )}
        >
          <Wrench size={16} /> Agent
        </Link>
        <Link
          href="/code"
          className={clsx(
            "flex items-center gap-2 px-3 py-2 rounded-md hover:bg-background",
            pathname?.startsWith("/code") && "bg-background"
          )}
        >
          <Code2 size={16} /> Code workspace
        </Link>
        <Link
          href="/docs"
          className={clsx(
            "flex items-center gap-2 px-3 py-2 rounded-md hover:bg-background",
            pathname?.startsWith("/docs") && "bg-background"
          )}
        >
          <FileText size={16} /> Documents
        </Link>
      </div>

      <div className="px-2 pb-1 text-xs uppercase tracking-wider text-muted">
        Conversations
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5">
        {loading && <div className="px-3 py-2 text-sm text-muted">Loading…</div>}
        {!loading && items.length === 0 && (
          <div className="px-3 py-2 text-sm text-muted">No conversations yet.</div>
        )}
        {items.map((c) => (
          <div
            key={c.id}
            className={clsx(
              "group flex items-center justify-between px-3 py-1.5 rounded-md hover:bg-background cursor-pointer",
              activeId === c.id && "bg-background"
            )}
            onClick={() => router.push(`/chat/${c.id}`)}
          >
            <div className="flex items-center gap-2 min-w-0">
              <MessageSquare size={14} className="shrink-0 text-muted" />
              <span className="truncate text-sm">{c.title || "Untitled"}</span>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(c.id);
              }}
              className="opacity-0 group-hover:opacity-100 hover:text-red-400"
              title="Delete"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>

      <div className="p-2 border-t border-border">
        <Link
          href="/settings"
          className="flex items-center gap-2 px-3 py-2 rounded-md hover:bg-background"
        >
          <Settings size={16} /> Settings
        </Link>
      </div>
    </aside>
  );
}
