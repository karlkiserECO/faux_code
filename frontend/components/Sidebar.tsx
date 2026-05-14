"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ConversationSummary,
  deleteConversation,
  listConversations,
  pinConversation,
} from "@/lib/api";
import {
  Plus,
  MessageSquare,
  Trash2,
  Settings,
  Code2,
  FileText,
  Wrench,
  Search,
  Pin,
  PinOff,
  Rocket,
} from "lucide-react";
import clsx from "clsx";

type Group = { label: string; items: ConversationSummary[] };

export default function Sidebar({ activeId }: { activeId?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

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

  async function onPin(id: string, currentlyPinned: boolean) {
    await pinConversation(id, !currentlyPinned);
    await refresh();
  }

  const filtered = useMemo(
    () =>
      items.filter((c) =>
        search.trim()
          ? c.title.toLowerCase().includes(search.toLowerCase())
          : true
      ),
    [items, search]
  );

  const groups: Group[] = useMemo(() => groupByRecency(filtered), [filtered]);

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

      <div className="px-3 py-1">
        <div className="relative">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search conversations"
            className="w-full bg-background border border-border rounded-md pl-7 pr-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-muted"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2 mt-1">
        {loading && <div className="px-3 py-2 text-sm text-muted">Loading…</div>}
        {!loading && filtered.length === 0 && (
          <div className="px-3 py-2 text-sm text-muted">
            {search ? "No matching conversations." : "No conversations yet."}
          </div>
        )}
        {groups.map((g) => (
          <div key={g.label} className="mb-2">
            <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-muted">
              {g.label}
            </div>
            {g.items.map((c) => (
              <div
                key={c.id}
                className={clsx(
                  "group flex items-center justify-between px-3 py-1.5 rounded-md hover:bg-background cursor-pointer",
                  activeId === c.id && "bg-background"
                )}
                onClick={() => router.push(`/chat/${c.id}`)}
                title={c.title}
              >
                <div className="flex items-center gap-2 min-w-0">
                  {c.pinned ? (
                    <Pin size={12} className="shrink-0 text-accent" />
                  ) : (
                    <MessageSquare size={14} className="shrink-0 text-muted" />
                  )}
                  <span className="truncate text-sm">{c.title || "Untitled"}</span>
                </div>
                <div className="opacity-0 group-hover:opacity-100 flex items-center gap-0.5">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onPin(c.id, c.pinned);
                    }}
                    className="p-0.5 hover:text-accent"
                    title={c.pinned ? "Unpin" : "Pin"}
                  >
                    {c.pinned ? <PinOff size={12} /> : <Pin size={12} />}
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(c.id);
                    }}
                    className="p-0.5 hover:text-red-400"
                    title="Delete"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="p-2 border-t border-border space-y-0.5">
        <Link
          href="/welcome"
          className="flex items-center gap-2 px-3 py-2 rounded-md hover:bg-background"
        >
          <Rocket size={16} /> Welcome
        </Link>
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

function groupByRecency(items: ConversationSummary[]): Group[] {
  const pinned: ConversationSummary[] = [];
  const today: ConversationSummary[] = [];
  const yesterday: ConversationSummary[] = [];
  const week: ConversationSummary[] = [];
  const older: ConversationSummary[] = [];

  const now = Date.now();
  const day = 24 * 3600 * 1000;
  for (const c of items) {
    if (c.pinned) {
      pinned.push(c);
      continue;
    }
    const t = new Date(c.updated_at).getTime();
    const age = now - t;
    if (age < day) today.push(c);
    else if (age < 2 * day) yesterday.push(c);
    else if (age < 7 * day) week.push(c);
    else older.push(c);
  }
  const groups: Group[] = [];
  if (pinned.length) groups.push({ label: "Pinned", items: pinned });
  if (today.length) groups.push({ label: "Today", items: today });
  if (yesterday.length) groups.push({ label: "Yesterday", items: yesterday });
  if (week.length) groups.push({ label: "This week", items: week });
  if (older.length) groups.push({ label: "Older", items: older });
  return groups;
}
