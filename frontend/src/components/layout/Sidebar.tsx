"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FlaskConical, Play, Settings, Beaker, LineChart } from "lucide-react";

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
};

const nav: NavItem[] = [
  { href: "/datasets", label: "Datasets", icon: FlaskConical },
  { href: "/run", label: "Run", icon: Play },
  { href: "/evals", label: "Evals", icon: LineChart },
  { href: "/experiments", label: "Experiments", icon: Beaker },
  { href: "/configs", label: "Configs", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden lg:flex fixed left-0 top-0 bottom-0 w-[260px] bg-eggshell border-r border-linen flex-col overflow-hidden z-40">
      <div className="px-4 py-5 border-b border-linen">
        <div className="font-serif text-xl tracking-tight text-ink">RAG Benchmark</div>
        <div className="mt-1 font-sans text-sm text-ash">Benchmarks & configs</div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
        {nav.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={[
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-sans font-medium transition-colors duration-100",
                isActive
                  ? "bg-linen text-charcoal"
                  : "text-ash hover:bg-linen hover:text-charcoal",
              ].join(" ")}
            >
              <item.icon className="h-[18px] w-[18px]" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

