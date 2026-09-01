import { NavLink } from "react-router-dom";

const links = [
  { to: "/corpora", label: "Corpora", hint: "Documents" },
  { to: "/configurations", label: "Configurations", hint: "Parse + chunk" },
  { to: "/components", label: "Components", hint: "Registry" },
];

export function Sidebar() {
  return (
    <aside className="flex w-56 shrink-0 flex-col bg-sidebar text-paper">
      <div className="border-b border-white/10 px-4 py-5">
        <p className="font-mono text-[11px] tracking-[0.18em] text-rust uppercase">RAG Bench</p>
        <p className="mt-1 text-sm text-sidebar-muted">Measure, then choose.</p>
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-3">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              `rounded-md px-3 py-2 ${isActive ? "bg-white/10 text-white" : "text-sidebar-muted hover:bg-white/5 hover:text-paper"}`
            }
          >
            <span className="block text-sm font-medium">{link.label}</span>
            <span className="block text-xs opacity-70">{link.hint}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
