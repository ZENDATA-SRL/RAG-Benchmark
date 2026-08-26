"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";

export function XlsxUpload({
  label,
  help,
  accept = ".xlsx,.csv,text/csv",
  onUpload,
  disabled,
}: {
  label: string;
  help?: string;
  accept?: string;
  disabled?: boolean;
  onUpload: (file: File) => Promise<{ inserted: number }>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">("idle");
  const [message, setMessage] = useState<string>("");

  const locked = disabled === true || status === "done";
  const canUpload = useMemo(
    () => !!file && status !== "uploading" && !locked,
    [file, status, locked],
  );

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <div className="font-sans text-sm font-medium text-charcoal">{label}</div>
        {help ? <div className="font-sans text-sm text-ash">{help}</div> : null}
      </div>

      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <input
          type="file"
          accept={accept}
          disabled={locked || status === "uploading"}
          className="block w-full text-sm font-sans text-slate file:mr-4 file:rounded-md file:border file:border-linen file:bg-eggshell file:px-4 file:py-2 file:text-sm file:font-medium file:text-charcoal hover:file:bg-linen disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:file:bg-eggshell"
          onChange={(e) => {
            if (locked || status === "uploading") return;
            setMessage("");
            setStatus("idle");
            setFile(e.target.files?.[0] ?? null);
          }}
        />

        <Button
          type="button"
          disabled={!canUpload}
          onClick={async () => {
            if (!file || locked) return;
            setStatus("uploading");
            setMessage("");
            try {
              const res = await onUpload(file);
              setStatus("done");
              setMessage(`Uploaded. Inserted ${res.inserted}.`);
            } catch (e) {
              setStatus("error");
              setMessage(e instanceof Error ? e.message : "Upload failed.");
            }
          }}
        >
          {status === "uploading" ? "Uploading…" : locked ? "Uploaded" : "Upload"}
        </Button>
      </div>

      {message ? (
        <div
          className={`font-sans text-sm ${
            status === "error" ? "text-red-700" : status === "done" ? "text-sage" : "text-ash"
          }`}
        >
          {message}
        </div>
      ) : null}
    </div>
  );
}

