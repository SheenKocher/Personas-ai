import { NavLink, Outlet } from "react-router-dom";
import { NAV } from "@/constants/testIds";
import { Grid3X3, Users, FileText, GitCompareArrows, Play } from "lucide-react";

const navItems = [
  { to: "/", label: "Live Grid", icon: Grid3X3, testId: NAV.liveGrid },
  { to: "/persona-panels", label: "Persona Panels", icon: Users, testId: NAV.personaPanels },
  { to: "/reports", label: "Reports", icon: FileText, testId: NAV.reports },
  { to: "/cross-stage-diff", label: "Cross-Stage Diff", icon: GitCompareArrows, testId: NAV.crossStageDiff },
  { to: "/new-run", label: "New Run", icon: Play, testId: NAV.newRun },
];

export default function Layout() {
  return (
    <div className="min-h-screen" style={{ background: "#0B0F1A" }}>
      {/* Top Navigation Bar */}
      <nav
        className="sticky top-0 z-40 flex items-center gap-8 px-6 h-14"
        style={{
          background: "#0B0F1A",
          borderBottom: "0.5px solid #1E293B",
        }}
      >
        {/* Logo */}
        <NavLink to="/" data-testid={NAV.logo} className="flex items-center gap-3 mr-4 shrink-0">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium"
            style={{ background: "#2DD4BF", color: "#06231F" }}
          >
            ST
          </div>
          <span className="text-sm font-medium" style={{ color: "#F1F5F9" }}>
            SynthTest
          </span>
        </NavLink>

        {/* Nav Links */}
        <div className="flex items-center gap-1 h-full overflow-x-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              data-testid={item.testId}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors h-full relative ${
                  isActive ? "nav-active-underline" : ""
                }`
              }
              style={({ isActive }) => ({
                color: isActive ? "#2DD4BF" : "#64748B",
              })}
            >
              <item.icon className="w-4 h-4" />
              <span className="whitespace-nowrap">{item.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Page Content */}
      <main className="px-6 py-6 max-w-[1440px] mx-auto">
        <Outlet />
      </main>
    </div>
  );
}
