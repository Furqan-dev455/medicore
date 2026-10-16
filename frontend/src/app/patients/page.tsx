"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { usePortalRole } from "@/components/usePortalRole";
import { RecordDialog, RecordField } from "@/components/RecordDialog";
import { fetchAuthenticatedJson, PatientApi } from "@/data/hospitalApi";

const fields: RecordField[] = [
  { name: "name", label: "Full name" },
  { name: "age", label: "Age", type: "number", min: "0" },
  { name: "gender", label: "Gender", type: "select", options: [
    { value: "Male", label: "Male" },
    { value: "Female", label: "Female" },
    { value: "Other", label: "Other" },
  ] },
  { name: "phone", label: "Phone" },
  { name: "address", label: "Address", type: "textarea" },
  { name: "medical_history", label: "Medical history", type: "textarea", required: false },
];

export default function PatientsPage() {
  const role = usePortalRole();
  const [patients, setPatients] = useState<PatientApi[]>([]);
  const [editing, setEditing] = useState<PatientApi | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [error, setError] = useState("");

  async function loadPatients() {
    const data = await fetchAuthenticatedJson<{ patients: PatientApi[] }>("/api/patients/");
    setPatients(data.patients);
  }

  useEffect(() => {
    fetchAuthenticatedJson<{ patients: PatientApi[] }>("/api/patients/")
      .then((data) => setPatients(data.patients))
      .catch((loadError) => setError(loadError.message));
  }, []);

  return (
    <AppShell>
      <div className="space-y-6">
        <header className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-600">Records</p>
            <h2 className="mt-2 text-3xl font-bold text-slate-900">Patients</h2>
          </div>
          {role === "Admin" && <button className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-600" onClick={() => { setEditing(null); setDialogOpen(true); }}>Add patient</button>}
        </header>

        {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50 text-left text-sm text-slate-600">
              <tr>
                <th className="px-5 py-4 font-medium">Patient</th>
                <th className="px-5 py-4 font-medium">Age</th>
                <th className="px-5 py-4 font-medium">Gender</th>
                <th className="px-5 py-4 font-medium">Phone</th>
                <th className="px-5 py-4 font-medium">Status</th>
                <th className="px-5 py-4 font-medium">Actions</th>
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
                  <td className="px-5 py-4">
                    {role === "Admin" && <button className="font-medium text-sky-700 hover:text-sky-900" onClick={() => { setEditing(patient); setDialogOpen(true); }}>Edit</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {dialogOpen && <RecordDialog
        title={editing ? "Edit patient" : "Add patient"}
        resource="patients"
        fields={fields}
        initialValue={editing ?? undefined}
        onClose={() => setDialogOpen(false)}
        onSaved={loadPatients}
      />}
    </AppShell>
  );
}
