"use client";

import { AlertTriangle } from "lucide-react";

export default function ApprovalModal({
  request,
  onApprove,
  onDeny,
}: {
  request: { op: string; args: any };
  onApprove: () => void;
  onDeny: () => void;
}) {
  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-lg max-w-xl w-full p-5 space-y-3">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-yellow-500/15 text-yellow-400 p-2">
            <AlertTriangle size={20} />
          </div>
          <div>
            <div className="font-medium">Approve action: {request.op}</div>
            <div className="text-sm text-muted">
              The agent wants to take a write or shell action. Review and approve or deny.
            </div>
          </div>
        </div>
        <pre className="bg-background border border-border rounded p-3 text-xs overflow-x-auto">
          {JSON.stringify(request.args, null, 2)}
        </pre>
        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onDeny}
            className="px-3 py-1.5 rounded-md border border-border hover:bg-background"
          >
            Deny
          </button>
          <button
            onClick={onApprove}
            className="px-3 py-1.5 rounded-md bg-accent text-background hover:opacity-90"
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
