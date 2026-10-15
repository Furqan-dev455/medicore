"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { fetchJson, PatientApi } from "@/data/hospitalApi";

export default function PatientsPage() {
  const [patients, setPatients] = useState<PatientApi[]>([]);

  useEffect(() => {
    fetchJson<{ patients: PatientApi[] }>("/api/patients/")
      .then((data) => setPatients(data.patients))
      .catch((error) => console.error("Patients API error:", error));
  }, []);

  return (
    <AppShell>
      <div className="space-y-6">
        <header className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-600">Records</p>
            <h2 className="mt-2 text-3xl font-bold text-slate-900">Patients</h2>
          </div>
          <button className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500">Add patient</button>
        </header>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50 text-left text-sm text-slate-600">
              <tr>
                <th className="px-5 py-4 font-medium">Patient</th>
                <th className="px-5 py-4 font-medium">Age</th>
                <th className="px-5 py-4 font-medium">Gender</th>
                <th className="px-5 py-4 font-medium">Phone</th>
                <th className="px-5 py-4 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-sm text-slate-700">
              {patients.map((patient) => (
                <tr key={patient.id} className="hover:bg-slate-50">
                  <td className="px-5 py-4">
                    <div>
                      <p className="font-medium text-slate-900">{patient.name}</p>
                      <p className="text-xs text-slate-500">{patient.address}</p>
                    </div>
                  </td>
                  <td className="px-5 py-4">{patient.age}</td>
                  <td className="px-5 py-4">{patient.gender}</td>
                  <td className="px-5 py-4">{patient.phone}</td>
                  <td className="px-5 py-4">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                      patient.status === "Active"
                        ? "bg-emerald-100 text-emerald-700"
                        : patient.status === "Follow Up"
                          ? "bg-amber-100 text-amber-700"
                          : "bg-slate-200 text-slate-700"
                    }`}>
                      {patient.status}
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
