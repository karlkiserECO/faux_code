"use client";

import { useEffect, useState } from "react";
import { ChevronRight, ChevronDown, File as FileIcon, Folder } from "lucide-react";
import clsx from "clsx";
import { getWorkspaceTree, WorkspaceEntry } from "@/lib/api";

type TreeNodeProps = {
  entry: WorkspaceEntry;
  root: string;
  level: number;
  activePath?: string;
  onSelect: (path: string) => void;
};

function TreeNode({ entry, root, level, activePath, onSelect }: TreeNodeProps) {
  const [expanded, setExpanded] = useState(false);
  const [children, setChildren] = useState<WorkspaceEntry[] | null>(null);
  const [loading, setLoading] = useState(false);

  async function toggle() {
    if (!entry.is_dir) {
      onSelect(entry.path);
      return;
    }
    if (!expanded && children === null) {
      setLoading(true);
      try {
        const items = await getWorkspaceTree(entry.path, root);
        setChildren(items);
      } catch {
        setChildren([]);
      }
      setLoading(false);
    }
    setExpanded((v) => !v);
  }

  const isActive = !entry.is_dir && entry.path === activePath;

  return (
    <div>
      <button
        onClick={toggle}
        className={clsx(
          "w-full flex items-center gap-1 px-2 py-0.5 text-sm hover:bg-background rounded",
          isActive && "bg-accent/15 text-accent"
        )}
        style={{ paddingLeft: 4 + level * 12 }}
      >
        {entry.is_dir ? (
          expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />
        ) : (
          <span className="w-3" />
        )}
        {entry.is_dir ? (
          <Folder size={14} className="text-accent/80" />
        ) : (
          <FileIcon size={14} className="text-muted" />
        )}
        <span className="truncate">{entry.name}</span>
      </button>
      {entry.is_dir && expanded && (
        <div>
          {loading && (
            <div className="text-xs text-muted px-2 py-1" style={{ paddingLeft: 16 + level * 12 }}>
              loading…
            </div>
          )}
          {(children || []).map((c) => (
            <TreeNode
              key={c.path}
              entry={c}
              root={root}
              level={level + 1}
              activePath={activePath}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function FileTree({
  root,
  activePath,
  onSelect,
}: {
  root: string;
  activePath?: string;
  onSelect: (path: string) => void;
}) {
  const [entries, setEntries] = useState<WorkspaceEntry[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const items = await getWorkspaceTree("", root);
      setEntries(items);
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [root]);

  return (
    <div className="overflow-y-auto h-full text-sm">
      <div className="px-3 py-2 text-xs uppercase tracking-wider text-muted flex items-center justify-between">
        <span>Files</span>
        <button onClick={load} className="text-muted hover:text-foreground">↻</button>
      </div>
      {loading && <div className="px-3 py-1 text-xs text-muted">loading…</div>}
      {!loading && entries.length === 0 && (
        <div className="px-3 py-1 text-xs text-muted">(empty)</div>
      )}
      <div className="px-1">
        {entries.map((e) => (
          <TreeNode
            key={e.path}
            entry={e}
            root={root}
            level={0}
            activePath={activePath}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}
