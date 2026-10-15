"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { AppointmentApi, fetchJson } from "@/data/hospitalApi";

export default function AppointmentsPage() {
  const [appointments, setAppointments] = useState<AppointmentApi[]>([]);

  useEffect(() => {
    fetchJson<{ appointments: AppointmentApi[] }>("/api/appointments/")
      .then((data) => setAppointments(data.appointments))
      .catch((error) => console.error("Appointments API error:", error));
  }, []);

  return (
    <AppShell>
      <div className="space-y-6">
        <header className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-600">Schedule</p>
            <h2 className="mt-2 text-3xl font-bold text-slate-900">Appointments</h2>
          </div>
          <button className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500">Book appointment</button>
        </header>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50 text-left text-sm text-slate-600">
              <tr>
                <th className="px-5 py-4 font-medium">Patient</th>
                <th className="px-5 py-4 font-medium">Doctor</th>
                <th className="px-5 py-4 font-medium">Date</th>
                <th className="px-5 py-4 font-medium">Time</th>
                <th className="px-5 py-4 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-sm text-slate-700">
              {appointments.map((appointment) => (
                <tr key={appointment.id} className="hover:bg-slate-50">
                  <td className="px-5 py-4 font-medium text-slate-900">{appointment.patient}</td>
                  <td className="px-5 py-4">{appointment.doctor}</td>
                  <td className="px-5 py-4">{appointment.date}</td>
                  <td className="px-5 py-4">{appointment.time}</td>
                  <td className="px-5 py-4">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                      appointment.status === "Scheduled"
                        ? "bg-sky-100 text-sky-700"
                        : appointment.status === "Completed"
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-rose-100 text-rose-700"
                    }`}>
                      {appointment.status}
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
