"use client";

import { useEffect, useRef, useState } from "react";
import Sidebar from "@/components/Sidebar";
import {
  deleteRagCollection,
  listRagDocuments,
  RagDocument,
  searchRag,
  uploadRagFile,
} from "@/lib/api";
import { FileText, Upload, Trash2 } from "lucide-react";

export default function DocsPage() {
  const [docs, setDocs] = useState<RagDocument[]>([]);
  const [collection, setCollection] = useState("default");
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  async function refresh() {
    try {
      setDocs(await listRagDocuments());
    } catch {}
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleUpload(file: File) {
    setUploading(true);
    try {
      await uploadRagFile(file, collection);
      await refresh();
    } catch (e: any) {
      alert(`Upload failed: ${e?.message || e}`);
    } finally {
      setUploading(false);
    }
  }

  async function runSearch() {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const r = await searchRag({ query, top_k: 5, collection });
      setResults(r.hits || []);
    } catch (e: any) {
      alert(`Search failed: ${e?.message || e}`);
    } finally {
      setSearching(false);
    }
  }

  async function dropCollection(name: string) {
    if (!confirm(`Drop collection "${name}" and all its docs?`)) return;
    await deleteRagCollection(name);
    await refresh();
  }

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto p-6 space-y-6">
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <FileText size={22} /> Documents
          </h1>
          <p className="text-sm text-muted">
            Upload documents to build a local knowledge base. The agent's{" "}
            <code className="text-accent">rag_search</code> tool will query these.
            Embeddings are generated locally via Ollama (model:{" "}
            <code>nomic-embed-text</code>).
          </p>

          <section className="rounded-lg border border-border bg-card p-4 space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-sm">Collection:</span>
              <input
                value={collection}
                onChange={(e) => setCollection(e.target.value)}
                className="bg-background border border-border rounded-md px-2 py-1 text-sm w-48 focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="file"
                ref={inputRef}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleUpload(f);
                }}
                className="hidden"
                accept=".pdf,.txt,.md,.csv,.json,.py,.ts,.tsx,.js,.jsx,.html,.css"
              />
              <button
                onClick={() => inputRef.current?.click()}
                disabled={uploading}
                className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-accent text-background disabled:opacity-40 text-sm"
              >
                <Upload size={14} /> {uploading ? "Uploading…" : "Upload file"}
              </button>
              <span className="text-xs text-muted">
                PDF, TXT, MD, CSV, JSON, source code.
              </span>
            </div>
          </section>

          <section className="space-y-2">
            <h2 className="text-sm uppercase tracking-wider text-muted">
              Indexed documents
            </h2>
            {docs.length === 0 && (
              <div className="text-sm text-muted">No documents indexed yet.</div>
            )}
            <div className="space-y-1">
              {Object.entries(groupByCollection(docs)).map(([col, ds]) => (
                <div key={col} className="rounded-lg border border-border bg-card p-3">
                  <div className="flex items-center justify-between mb-1">
                    <div className="font-medium text-sm">
                      {col}{" "}
                      <span className="text-muted text-xs">
                        ({ds.length} doc{ds.length === 1 ? "" : "s"})
                      </span>
                    </div>
                    <button
                      onClick={() => dropCollection(col)}
                      className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1"
                    >
                      <Trash2 size={12} /> drop
                    </button>
                  </div>
                  <ul className="text-sm space-y-0.5">
                    {ds.map((d) => (
                      <li key={d.id} className="flex justify-between text-muted">
                        <span className="truncate">{d.title}</span>
                        <span className="ml-2 text-xs">{d.n_chunks} chunks</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-lg border border-border bg-card p-4 space-y-3">
            <h2 className="text-sm uppercase tracking-wider text-muted">
              Search
            </h2>
            <div className="flex gap-2">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && runSearch()}
                placeholder="Semantic query…"
                className="flex-1 bg-background border border-border rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
              />
              <button
                onClick={runSearch}
                disabled={searching || !query.trim()}
                className="px-4 py-1.5 rounded-md bg-accent text-background disabled:opacity-40 text-sm"
              >
                {searching ? "Searching…" : "Search"}
              </button>
            </div>
            {results.length > 0 && (
              <div className="space-y-2">
                {results.map((h, i) => (
                  <div key={i} className="border border-border rounded-md p-2 bg-background/50">
                    <div className="flex items-center justify-between text-xs text-muted">
                      <span>{h.title || "(untitled)"}</span>
                      <span>score {Number(h.score || 0).toFixed(3)}</span>
                    </div>
                    <div className="text-sm whitespace-pre-wrap mt-1">{h.text}</div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

function groupByCollection(docs: RagDocument[]) {
  const out: Record<string, RagDocument[]> = {};
  for (const d of docs) {
    out[d.collection] = out[d.collection] || [];
    out[d.collection].push(d);
  }
  return out;
}
