"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { usePortalRole } from "@/components/usePortalRole";
import { RecordDialog, RecordField } from "@/components/RecordDialog";
import { DoctorApi, fetchAuthenticatedJson } from "@/data/hospitalApi";

const fields: RecordField[] = [
  { name: "name", label: "Full name" },
  { name: "specialization", label: "Specialization" },
  { name: "phone", label: "Phone" },
  { name: "email", label: "Email", type: "email" },
];

export default function DoctorsPage() {
  const role = usePortalRole();
  const [doctors, setDoctors] = useState<DoctorApi[]>([]);
  const [editing, setEditing] = useState<DoctorApi | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [error, setError] = useState("");

  async function loadDoctors() {
    const data = await fetchAuthenticatedJson<{ doctors: DoctorApi[] }>("/api/doctors/");
    setDoctors(data.doctors);
  }

  useEffect(() => {
    fetchAuthenticatedJson<{ doctors: DoctorApi[] }>("/api/doctors/")
      .then((data) => setDoctors(data.doctors))
      .catch((loadError) => setError(loadError.message));
  }, []);

  return (
    <AppShell>
      <div className="space-y-6">
        <header className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-600">Team</p>
            <h2 className="mt-2 text-3xl font-bold text-slate-900">Doctors</h2>
          </div>
          {role === "Admin" && <button className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-600" onClick={() => { setEditing(null); setDialogOpen(true); }}>Add doctor</button>}
        </header>

        {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {doctors.map((doctor) => (
            <div key={doctor.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 flex justify-end">
                {role === "Admin" && <button className="font-medium text-sky-700 hover:text-sky-900" onClick={() => { setEditing(doctor); setDialogOpen(true); }}>Edit</button>}
              </div>
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
      {dialogOpen && <RecordDialog
        title={editing ? "Edit doctor" : "Add doctor"}
        resource="doctors"
        fields={fields}
        initialValue={editing ?? undefined}
        onClose={() => setDialogOpen(false)}
        onSaved={loadDoctors}
      />}
    </AppShell>
  );
}
