"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { NewRecordDialog } from "@/components/NewRecordDialog";
import { StatCard } from "@/components/StatCard";
import { ApiError, DashboardData, fetchAuthenticatedJson } from "@/data/hospitalApi";

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [newRecordOpen, setNewRecordOpen] = useState(false);

  const loadDashboard = useCallback(async () => {
    const dashboard = await fetchAuthenticatedJson<DashboardData>("/api/dashboard/");
    setData(dashboard);
  }, []);

  useEffect(() => {
    loadDashboard()
      .catch((error) => {
        if (error instanceof ApiError && error.status === 401) {
          router.replace("/login");
          return;
        }
        console.error("Dashboard API error:", error);
      });
  }, [loadDashboard, router]);

  if (!data) {
    return (
      <AppShell>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-slate-500 shadow-sm">
          Loading dashboard...
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-8">
        <header className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-600">Overview</p>
            <h2 className="mt-2 text-3xl font-bold text-slate-900">Dashboard</h2>
          </div>
          {(data.role === "Admin" || data.role === "Receptionist") && (
            <button className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-sky-500" onClick={() => setNewRecordOpen(true)}>
              New record
            </button>
          )}
        </header>

        <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {data.stats.map((stat) => (
            <StatCard
              key={stat.label}
              label={stat.label}
              value={String(stat.value)}
              change={stat.change}
              tone={stat.tone as "emerald" | "blue" | "violet" | "amber"}
            />
          ))}
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-xl font-semibold text-slate-900">Upcoming appointments</h3>
              <span className="text-sm text-slate-500">This week</span>
            </div>

            <div className="space-y-4">
              {data.recent_appointments.map((item) => (
                <div key={item.id} className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div>
                    <p className="font-medium text-slate-900">{item.patient}</p>
                    <p className="text-sm text-slate-500">{item.doctor}</p>
                  </div>
                  <div className="text-right text-sm text-slate-600">
                    <p>{item.date}</p>
                    <p>{item.time}</p>
                  </div>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                    item.status === "Scheduled"
                      ? "bg-sky-100 text-sky-700"
                      : item.status === "Completed"
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-rose-100 text-rose-700"
                  }`}>
                    {item.status}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="text-xl font-semibold text-slate-900">Recent billing</h3>
            <div className="mt-5 space-y-4">
              {data.bills.map((bill) => (
                <div key={bill.id} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-center justify-between">
                    <p className="font-medium text-slate-900">{bill.patient}</p>
                    <span className={`rounded-full px-2 py-1 text-xs font-medium ${
                      bill.status === "Paid"
                        ? "bg-emerald-100 text-emerald-700"
                        : bill.status === "Partial"
                          ? "bg-amber-100 text-amber-700"
                          : "bg-rose-100 text-rose-700"
                    }`}>
                      {bill.status}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-slate-500">Total: ${bill.total.toLocaleString()}</p>
                  <p className="text-sm text-slate-500">Paid: ${bill.paid.toLocaleString()}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
      {newRecordOpen && (
        <NewRecordDialog
          role={data.role === "Receptionist" ? "Receptionist" : "Admin"}
          onClose={() => setNewRecordOpen(false)}
          onSaved={loadDashboard}
        />
      )}
    </AppShell>
  );
}
