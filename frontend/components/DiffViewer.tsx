"use client";

import { useMemo } from "react";

type DiffLine =
  | { type: "context"; text: string; oldNo: number | null; newNo: number | null }
  | { type: "added"; text: string; newNo: number }
  | { type: "removed"; text: string; oldNo: number };

/**
 * Compute a side-by-side line diff using a simple LCS, sufficient for small
 * agent edits. Not meant to compete with `diff-match-patch`.
 */
function computeDiff(oldText: string, newText: string): DiffLine[] {
  const a = oldText.split("\n");
  const b = newText.split("\n");
  const m = a.length;
  const n = b.length;
  // LCS DP — for large files this becomes expensive; cap at 5000 lines.
  const limit = 5000;
  if (m > limit || n > limit) {
    return [
      { type: "context", text: "[diff truncated: file too large for inline view]", oldNo: null, newNo: null },
    ];
  }
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (a[i] === b[j]) dp[i][j] = dp[i + 1][j + 1] + 1;
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0, j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      out.push({ type: "context", text: a[i], oldNo: i + 1, newNo: j + 1 });
      i++; j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ type: "removed", text: a[i], oldNo: i + 1 });
      i++;
    } else {
      out.push({ type: "added", text: b[j], newNo: j + 1 });
      j++;
    }
  }
  while (i < m) { out.push({ type: "removed", text: a[i], oldNo: i + 1 }); i++; }
  while (j < n) { out.push({ type: "added", text: b[j], newNo: j + 1 }); j++; }
  return out;
}

export default function DiffViewer({
  oldText,
  newText,
  fileName,
  context = 3,
}: {
  oldText: string;
  newText: string;
  fileName?: string;
  context?: number;
}) {
  const lines = useMemo(() => computeDiff(oldText, newText), [oldText, newText]);

  // Hide stretches of unchanged context > 2*context+1.
  const visible: (DiffLine | { type: "skip"; n: number })[] = [];
  let run: DiffLine[] = [];
  for (const ln of lines) {
    if (ln.type === "context") run.push(ln);
    else {
      flushRun(run, context, visible);
      run = [];
      visible.push(ln);
    }
  }
  flushRun(run, context, visible);

  const stats = useMemo(() => {
    let added = 0, removed = 0;
    for (const l of lines) {
      if (l.type === "added") added++;
      else if (l.type === "removed") removed++;
    }
    return { added, removed };
  }, [lines]);

  if (stats.added === 0 && stats.removed === 0) {
    return (
      <div className="text-xs text-muted px-3 py-2">
        No changes{fileName ? ` in ${fileName}` : ""}.
      </div>
    );
  }

  return (
    <div className="border border-border rounded-md overflow-hidden">
      <div className="px-3 py-1.5 border-b border-border bg-background/40 text-xs flex items-center gap-2">
        {fileName && <span className="font-mono">{fileName}</span>}
        <span className="text-emerald-300">+{stats.added}</span>
        <span className="text-red-300">-{stats.removed}</span>
      </div>
      <div className="font-mono text-[12.5px] overflow-x-auto leading-snug">
        {visible.map((row, idx) => {
          if (row.type === "skip") {
            return (
              <div
                key={idx}
                className="px-3 py-0.5 bg-card/30 text-muted text-[11px] border-y border-border/60"
              >
                … {row.n} unchanged line{row.n === 1 ? "" : "s"}
              </div>
            );
          }
          const bg =
            row.type === "added"
              ? "bg-emerald-500/10"
              : row.type === "removed"
              ? "bg-red-500/10"
              : "";
          const marker =
            row.type === "added" ? "+" : row.type === "removed" ? "-" : " ";
          const markerColor =
            row.type === "added"
              ? "text-emerald-300"
              : row.type === "removed"
              ? "text-red-300"
              : "text-muted";
          const oldNo = row.type === "context" || row.type === "removed" ? row.oldNo : "";
          const newNo = row.type === "context" || row.type === "added" ? row.newNo : "";
          return (
            <div key={idx} className={`flex ${bg}`}>
              <span className="w-10 text-right pr-2 text-[10px] text-muted shrink-0 select-none">
                {oldNo ?? ""}
              </span>
              <span className="w-10 text-right pr-2 text-[10px] text-muted shrink-0 select-none">
                {newNo ?? ""}
              </span>
              <span className={`w-4 text-center ${markerColor} shrink-0 select-none`}>
                {marker}
              </span>
              <span className="whitespace-pre">{row.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function flushRun(
  run: DiffLine[],
  context: number,
  out: (DiffLine | { type: "skip"; n: number })[]
) {
  if (run.length === 0) return;
  const hasChangesBefore = out.length > 0;
  const hasChangesAfter = true; // caller usually flushes before a change
  if (!hasChangesBefore && run.length > context) {
    out.push({ type: "skip", n: run.length - context });
    for (const l of run.slice(-context)) out.push(l);
  } else if (run.length > 2 * context) {
    for (const l of run.slice(0, context)) out.push(l);
    out.push({ type: "skip", n: run.length - 2 * context });
    for (const l of run.slice(-context)) out.push(l);
  } else {
    for (const l of run) out.push(l);
  }
  // Suppress trailing context that isn't followed by a change.
  // (Handled by caller — final flush keeps everything but we never want too many tails.)
  if (!hasChangesAfter && run.length > context) {
    // can't happen with current caller pattern
  }
}
