export type ApiErrorBody = {
  code: string;
  message: string;
  details: Record<string, unknown>;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseApiError(status: number, payload: unknown): ApiError {
  if (isRecord(payload) && typeof payload.code === "string" && typeof payload.message === "string") {
    return new ApiError(status, {
      code: payload.code,
      message: payload.message,
      details: isRecord(payload.details) ? payload.details : {},
    });
  }

  if (isRecord(payload) && Array.isArray(payload.detail)) {
    const first = payload.detail[0];
    const loc = isRecord(first) && Array.isArray(first.loc) ? first.loc.join(".") : "";
    const msg = isRecord(first) && typeof first.msg === "string" ? first.msg : "validation failed";
    return new ApiError(status, {
      code: "validation_error",
      message: loc ? `invalid parameter at ${loc}: ${msg}` : msg,
      details: { field_path: loc, reason: msg },
    });
  }

  if (isRecord(payload) && typeof payload.detail === "string") {
    return new ApiError(status, { code: "http_error", message: payload.detail, details: {} });
  }

  return new ApiError(status, {
    code: "http_error",
    message: `request failed with status ${status}`,
    details: {},
  });
}

export function errorToastText(error: unknown): string {
  if (error instanceof ApiError) {
    return `${error.message} (${error.code})`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong";
}
