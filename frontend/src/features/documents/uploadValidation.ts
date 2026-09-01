import type { FileOutcome, UploadFileResult } from "@/api/types";

export const ALLOWED_EXTENSIONS = [".pdf"];
export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;

export type LocalReject = {
  filename: string;
  outcome: Extract<FileOutcome, "skipped_unsupported" | "failed">;
  error_reason: string;
};

export function classifyFile(file: File): LocalReject | null {
  const name = file.name.toLowerCase();
  const supported = ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext));
  if (!supported) {
    return {
      filename: file.name,
      outcome: "skipped_unsupported",
      error_reason: `unsupported extension (allowed: ${ALLOWED_EXTENSIONS.join(", ")})`,
    };
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return {
      filename: file.name,
      outcome: "failed",
      error_reason: `file too large: ${file.size} bytes (max ${MAX_UPLOAD_BYTES})`,
    };
  }
  if (file.size === 0) {
    return {
      filename: file.name,
      outcome: "failed",
      error_reason: "empty file",
    };
  }
  return null;
}

export function partitionFiles(files: File[]): { accepted: File[]; rejected: LocalReject[] } {
  const accepted: File[] = [];
  const rejected: LocalReject[] = [];
  for (const file of files) {
    const reject = classifyFile(file);
    if (reject) {
      rejected.push(reject);
    } else {
      accepted.push(file);
    }
  }
  return { accepted, rejected };
}

export function toUploadResult(reject: LocalReject): UploadFileResult {
  return {
    filename: reject.filename,
    outcome: reject.outcome,
    document_id: null,
    error_reason: reject.error_reason,
  };
}

export function countOutcomes(results: UploadFileResult[]): Record<FileOutcome, number> {
  const counts: Record<FileOutcome, number> = {
    imported: 0,
    skipped_duplicate: 0,
    skipped_unsupported: 0,
    failed: 0,
  };
  for (const result of results) {
    counts[result.outcome] += 1;
  }
  return counts;
}
