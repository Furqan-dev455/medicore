"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchJson, writeJson } from "@/data/hospitalApi";

export type PortalRole = "Admin" | "Doctor" | "Patient" | "Receptionist" | "Demo" | "Unassigned";

const navItems: Array<{ href: string; label: string; roles: PortalRole[] }> = [
  { href: "/", label: "Dashboard", roles: ["Admin", "Doctor", "Patient", "Receptionist", "Demo"] },
  { href: "/patients", label: "Patients", roles: ["Admin", "Doctor", "Patient", "Receptionist", "Demo"] },
  { href: "/doctors", label: "Doctors", roles: ["Admin", "Doctor", "Receptionist", "Demo"] },
  { href: "/appointments", label: "Appointments", roles: ["Admin", "Doctor", "Patient", "Receptionist", "Demo"] },
  { href: "/prescriptions", label: "Prescriptions", roles: ["Admin", "Doctor", "Patient"] },
  { href: "/pharmacy", label: "Pharmacy inventory", roles: ["Admin", "Doctor"] },
  { href: "/bills", label: "Bills", roles: ["Admin", "Patient", "Demo"] },
  { href: "/users", label: "User roles", roles: ["Admin"] },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<PortalRole>("Unassigned");
  const [checkingSession, setCheckingSession] = useState(true);

  useEffect(() => {
    if (pathname === "/demo") {
      const timer = window.setTimeout(() => {
        setUsername("Demo User");
        setRole("Demo");
        setCheckingSession(false);
      }, 0);
      return () => window.clearTimeout(timer);
    }

    if (new URLSearchParams(window.location.search).get("demo") === "1") {
      const timer = window.setTimeout(() => {
        setUsername("Demo User");
        setRole("Demo");
        setCheckingSession(false);
      }, 0);
      try {
        window.sessionStorage.setItem("medicore-demo-session", "true");
      } catch {
        // The demo query parameter still authorizes this page for the current navigation.
      }
      return () => window.clearTimeout(timer);
    }

    if (window.sessionStorage.getItem("medicore-demo-session") === "true") {
      const timer = window.setTimeout(() => {
        setUsername("Demo User");
        setRole("Demo");
        setCheckingSession(false);
      }, 0);
      return () => window.clearTimeout(timer);
    }

    fetchJson<{ authenticated: boolean; username?: string; role?: PortalRole }>("/api/auth/session")
      .then((session) => {
        if (!session.authenticated) {
          router.replace("/login");
          return;
        }
        setUsername(session.username ?? "");
        setRole(session.role ?? "Unassigned");
      })
      .catch(() => router.replace("/login"))
      .finally(() => setCheckingSession(false));
  }, [pathname, router]);

  async function signOut() {
    if (window.sessionStorage.getItem("medicore-demo-session") === "true") {
      window.sessionStorage.removeItem("medicore-demo-session");
      router.replace("/login");
      return;
    }
    try {
      await writeJson("/api/auth/logout", "POST", {});
      router.replace("/login");
    } catch (error) {
      console.error("Sign out failed:", error);
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800">
      <aside className="fixed inset-y-0 left-0 w-72 border-r border-slate-200 bg-slate-900 text-slate-100">
        <div className="flex h-20 items-center border-b border-slate-700 px-6">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-sky-300">MediCore</p>
            <h1 className="text-xl font-semibold">Hospital Portal</h1>
          </div>
        </div>

        <nav className="space-y-2 p-4">
          {navItems.filter((item) => item.roles.includes(role)).map((item) => {
            const active = pathname === item.href;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center rounded-lg px-4 py-3 text-sm font-medium transition ${
                  active
                    ? "bg-sky-500 text-white shadow-lg shadow-sky-500/20"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          {username && (
            <button
              className="w-full rounded-lg px-4 py-3 text-left text-sm font-medium text-slate-300 transition hover:bg-slate-800 hover:text-white"
              onClick={signOut}
              type="button"
            >
              Sign out ({username})
            </button>
          )}
        </nav>
      </aside>

      <main className="ml-72 min-h-screen p-8">
        <div className="mx-auto max-w-7xl">
          {checkingSession ? <p className="text-sm text-slate-500">Checking session...</p> : role === "Unassigned" ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900" role="status">
              Your account does not have a portal role yet. Ask an administrator to assign a role and link your patient or doctor profile.
            </div>
          ) : username && children}
        </div>
      </main>
    </div>
  );
}
