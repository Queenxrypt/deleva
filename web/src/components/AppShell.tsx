import { NavLink, Outlet } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/app", label: "Overview", end: true },
  { to: "/app/positions", label: "Positions" },
  { to: "/app/strategies", label: "Strategies" },
  { to: "/app/activity", label: "Activity" },
];

export function AppShell() {
  return (
    <div className="app-shell">
      <aside className="app-nav">
        <NavLink to="/" className="brand">
          DELEVA
        </NavLink>
        <span className="brand-sub">Aave V3 · Base</span>
        <nav>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="app-main">
        <div className="page">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
