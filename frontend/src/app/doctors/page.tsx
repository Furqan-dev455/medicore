"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { DoctorApi, fetchJson } from "@/data/hospitalApi";

export default function DoctorsPage() {
  const [doctors, setDoctors] = useState<DoctorApi[]>([]);

  useEffect(() => {
    fetchJson<{ doctors: DoctorApi[] }>("/api/doctors/")
      .then((data) => setDoctors(data.doctors))
      .catch((error) => console.error("Doctors API error:", error));
  }, []);

  return (
    <AppShell>
      <div className="space-y-6">
        <header className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-600">Team</p>
            <h2 className="mt-2 text-3xl font-bold text-slate-900">Doctors</h2>
          </div>
          <button className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500">Add doctor</button>
        </header>

        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {doctors.map((doctor) => (
            <div key={doctor.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-4 h-12 w-12 rounded-xl bg-sky-100 text-lg font-semibold text-sky-700 flex items-center justify-center">
                {doctor.name.split(" ").map((part) => part[0]).slice(0, 2).join("")}
              </div>
              <h3 className="text-xl font-semibold text-slate-900">{doctor.name}</h3>
              <p className="mt-1 text-sm text-sky-600">{doctor.specialization}</p>
              <div className="mt-4 space-y-2 text-sm text-slate-600">
                <p>{doctor.phone}</p>
                <p>{doctor.email}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
