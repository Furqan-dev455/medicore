"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { usePortalRole } from "@/components/usePortalRole";
import { RecordDialog, RecordField } from "@/components/RecordDialog";
import { AppointmentApi, DoctorApi, fetchAuthenticatedJson, PatientApi } from "@/data/hospitalApi";

export default function AppointmentsPage() {
  const role = usePortalRole();
  const [appointments, setAppointments] = useState<AppointmentApi[]>([]);
  const [patients, setPatients] = useState<PatientApi[]>([]);
  const [doctors, setDoctors] = useState<DoctorApi[]>([]);
  const [editing, setEditing] = useState<AppointmentApi | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [error, setError] = useState("");

  const fields: RecordField[] = [
    ...(role === "Patient" ? [] : [{ name: "patient", label: "Patient", type: "select" as const, options: patients.map((patient) => ({ value: patient.id, label: patient.name })) }]),
    { name: "doctor", label: "Doctor", type: "select", options: doctors.map((doctor) => ({ value: doctor.id, label: `${doctor.name} · ${doctor.specialization}` })) },
    { name: "appointment_date", label: "Date", type: "date" },
    { name: "appointment_time", label: "Time", type: "time" },
    ...(role === "Patient" ? [] : [{ name: "status", label: "Status", type: "select" as const, options: [
      { value: "Scheduled", label: "Scheduled" },
      { value: "Completed", label: "Completed" },
      { value: "Cancelled", label: "Cancelled" },
    ] }]),
    { name: "notes", label: "Notes", type: "textarea", required: false },
  ];

  async function loadData() {
    const [appointmentData, patientData, doctorData] = await Promise.all([
      fetchAuthenticatedJson<{ appointments: AppointmentApi[] }>("/api/appointments/"),
      fetchAuthenticatedJson<{ patients: PatientApi[] }>("/api/patients/"),
      fetchAuthenticatedJson<{ doctors: DoctorApi[] }>("/api/doctors/"),
    ]);
    setAppointments(appointmentData.appointments);
    setPatients(patientData.patients);
    setDoctors(doctorData.doctors);
  }

  useEffect(() => {
    Promise.all([
      fetchAuthenticatedJson<{ appointments: AppointmentApi[] }>("/api/appointments/"),
      fetchAuthenticatedJson<{ patients: PatientApi[] }>("/api/patients/"),
      fetchAuthenticatedJson<{ doctors: DoctorApi[] }>("/api/doctors/"),
    ])
      .then(([appointmentData, patientData, doctorData]) => {
        setAppointments(appointmentData.appointments);
        setPatients(patientData.patients);
        setDoctors(doctorData.doctors);
      })
      .catch((loadError) => setError(loadError.message));
  }, []);

  return (
    <AppShell>
      <div className="space-y-6">
        <header className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-600">Schedule</p>
            <h2 className="mt-2 text-3xl font-bold text-slate-900">Appointments</h2>
          </div>
          {(role === "Admin" || role === "Receptionist" || role === "Patient") && <button className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-600" onClick={() => { setEditing(null); setDialogOpen(true); }}>Book appointment</button>}
        </header>

        {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50 text-left text-sm text-slate-600">
              <tr>
                <th className="px-5 py-4 font-medium">Patient</th>
                <th className="px-5 py-4 font-medium">Doctor</th>
                <th className="px-5 py-4 font-medium">Date</th>
                <th className="px-5 py-4 font-medium">Time</th>
                <th className="px-5 py-4 font-medium">Status</th>
                <th className="px-5 py-4 font-medium">Actions</th>
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
                  <td className="px-5 py-4">
                    {role === "Admin" && <button className="font-medium text-sky-700 hover:text-sky-900" onClick={() => { setEditing(appointment); setDialogOpen(true); }}>Edit</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {dialogOpen && <RecordDialog
        title={editing ? "Edit appointment" : "Book appointment"}
        resource="appointments"
        fields={fields}
        initialValue={editing ? {
          id: editing.id,
          patient: editing.patient_id,
          doctor: editing.doctor_id,
          appointment_date: editing.date,
          appointment_time: editing.time,
          status: editing.status,
          notes: editing.notes,
        } : undefined}
        onClose={() => setDialogOpen(false)}
        onSaved={loadData}
      />}
    </AppShell>
  );
}
