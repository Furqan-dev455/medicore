"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/patients", label: "Patients" },
  { href: "/doctors", label: "Doctors" },
  { href: "/appointments", label: "Appointments" },
  { href: "/bills", label: "Bills" },
  { href: "/login", label: "Login" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

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
          {navItems.map((item) => {
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
        </nav>
      </aside>

      <main className="ml-72 min-h-screen p-8">
        <div className="mx-auto max-w-7xl">{children}</div>
      </main>
    </div>
  );
}
