"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { BillApi, fetchJson } from "@/data/hospitalApi";

export default function BillsPage() {
  const [bills, setBills] = useState<BillApi[]>([]);

  useEffect(() => {
    fetchJson<{ bills: BillApi[] }>("/api/bills/")
      .then((data) => setBills(data.bills))
      .catch((error) => console.error("Bills API error:", error));
  }, []);

  return (
    <AppShell>
      <div className="space-y-6">
        <header className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-600">Finance</p>
            <h2 className="mt-2 text-3xl font-bold text-slate-900">Bills</h2>
          </div>
          <button className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500">Create bill</button>
        </header>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50 text-left text-sm text-slate-600">
              <tr>
                <th className="px-5 py-4 font-medium">Patient</th>
                <th className="px-5 py-4 font-medium">Total</th>
                <th className="px-5 py-4 font-medium">Paid</th>
                <th className="px-5 py-4 font-medium">Balance</th>
                <th className="px-5 py-4 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-sm text-slate-700">
              {bills.map((bill) => (
                <tr key={bill.id} className="hover:bg-slate-50">
                  <td className="px-5 py-4 font-medium text-slate-900">{bill.patient}</td>
                  <td className="px-5 py-4">${bill.total.toLocaleString()}</td>
                  <td className="px-5 py-4">${bill.paid.toLocaleString()}</td>
                  <td className="px-5 py-4">${bill.balance.toLocaleString()}</td>
                  <td className="px-5 py-4">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                      bill.status === "Paid"
                        ? "bg-emerald-100 text-emerald-700"
                        : bill.status === "Partial"
                          ? "bg-amber-100 text-amber-700"
                          : "bg-rose-100 text-rose-700"
                    }`}>
                      {bill.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
