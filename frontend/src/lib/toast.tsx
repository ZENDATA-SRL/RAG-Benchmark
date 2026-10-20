import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type ToastKind = "info" | "success" | "error";

export type ToastItem = {
  id: number;
  kind: ToastKind;
  message: string;
};

type ToastApi = {
  push: (kind: ToastKind, message: string) => void;
  info: (message: string) => void;
  success: (message: string) => void;
  error: (message: string) => void;
};

let nextId = 1;
const listeners = new Set<(item: ToastItem) => void>();

function emit(kind: ToastKind, message: string): void {
  const item = { id: nextId++, kind, message };
  for (const listener of listeners) {
    listener(item);
  }
}

/** Imperative API so QueryClient caches can toast without a React tree. */
export const toast: ToastApi = {
  push: emit,
  info: (message) => emit("info", message),
  success: (message) => emit("success", message),
  error: (message) => emit("error", message),
};

const ToastContext = createContext<ToastApi>(toast);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  useEffect(() => {
    const listener = (item: ToastItem) => {
      setItems((current) => [...current, item]);
      window.setTimeout(() => dismiss(item.id), 6000);
    };
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, [dismiss]);

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <ol className="pointer-events-none fixed right-4 top-4 z-50 flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {items.map((item) => (
          <li
            key={item.id}
            className={`pointer-events-auto rounded-md border px-3 py-2 text-sm shadow-lg ${
              item.kind === "error"
                ? "border-rust/40 bg-white text-ink"
                : item.kind === "success"
                  ? "border-teal/40 bg-white text-ink"
                  : "border-line bg-white text-ink"
            }`}
          >
            <p>{item.message}</p>
          </li>
        ))}
      </ol>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  return useContext(ToastContext);
}
