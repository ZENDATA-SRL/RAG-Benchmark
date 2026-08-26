import { Sidebar } from "./Sidebar";

export function Shell({
  children,
  contentWidth = "chat",
}: {
  children: React.ReactNode;
  contentWidth?: "chat" | "wide";
}) {
  return (
    <div className="min-h-screen bg-paper text-text-primary overflow-x-hidden">
      <div className="flex min-h-screen items-stretch overflow-x-hidden">
        <Sidebar />
        <main className="flex-1 bg-paper overflow-x-hidden lg:pl-[260px]">
          <div
            className={[
              "mx-auto px-4 md:px-6 py-10",
              contentWidth === "wide" ? "w-full lg:w-4/5 max-w-none" : "w-full max-w-chat",
            ].join(" ")}
          >
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}

