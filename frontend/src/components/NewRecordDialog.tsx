"use client";

import { useEffect, useState } from "react";
import { RecordDialog, RecordField } from "@/components/RecordDialog";
import {
  DoctorApi,
  fetchAuthenticatedJson,
  PatientApi,
} from "@/data/hospitalApi";

type Resource = "patients" | "doctors" | "appointments" | "bills";

type NewRecordDialogProps = {
  role: "Admin" | "Receptionist";
  onClose: () => void;
  onSaved: () => Promise<void>;
};

const patientFields: RecordField[] = [
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

const doctorFields: RecordField[] = [
  { name: "name", label: "Full name" },
  { name: "specialization", label: "Specialization" },
  { name: "phone", label: "Phone" },
  { name: "email", label: "Email", type: "email" },
];

export function NewRecordDialog({ role, onClose, onSaved }: NewRecordDialogProps) {
  const [resource, setResource] = useState<Resource | null>(null);
  const [patients, setPatients] = useState<PatientApi[]>([]);
  const [doctors, setDoctors] = useState<DoctorApi[]>([]);
  const [loadingReferences, setLoadingReferences] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (resource !== "appointments" && resource !== "bills") return;

    let cancelled = false;
    setLoadingReferences(true);
    setError("");
    Promise.all([
      fetchAuthenticatedJson<{ patients: PatientApi[] }>("/api/patients/"),
      resource === "appointments"
        ? fetchAuthenticatedJson<{ doctors: DoctorApi[] }>("/api/doctors/")
        : Promise.resolve({ doctors: [] as DoctorApi[] }),
    ])
      .then(([patientData, doctorData]) => {
        if (cancelled) return;
        setPatients(patientData.patients);
        setDoctors(doctorData.doctors);
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Could not load related records.");
      })
      .finally(() => {
        if (!cancelled) setLoadingReferences(false);
      });

    return () => {
      cancelled = true;
    };
  }, [resource]);

  if (resource) {
    if (loadingReferences) {
      return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" role="presentation">
          <section className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl" aria-modal="true" role="dialog">
            <p className="text-sm text-slate-600">Loading related records...</p>
            <button className="mt-4 text-sm font-medium text-sky-700" onClick={() => setResource(null)} type="button">Back</button>
          </section>
        </div>
      );
    }

    const fields: RecordField[] = resource === "patients"
      ? patientFields
      : resource === "doctors"
        ? doctorFields
        : resource === "appointments"
          ? [
              { name: "patient", label: "Patient", type: "select", options: patients.map((patient) => ({ value: patient.id, label: patient.name })) },
              { name: "doctor", label: "Doctor", type: "select", options: doctors.map((doctor) => ({ value: doctor.id, label: `${doctor.name} · ${doctor.specialization}` })) },
              { name: "appointment_date", label: "Date", type: "date" },
              { name: "appointment_time", label: "Time", type: "time" },
              { name: "status", label: "Status", type: "select", options: [
                { value: "Scheduled", label: "Scheduled" },
                { value: "Completed", label: "Completed" },
                { value: "Cancelled", label: "Cancelled" },
              ] },
              { name: "notes", label: "Notes", type: "textarea", required: false },
            ]
          : [
              { name: "patient", label: "Patient", type: "select", options: patients.map((patient) => ({ value: patient.id, label: patient.name })) },
              { name: "total_amount", label: "Total amount", type: "number", min: "0.01", step: "0.01" },
              { name: "description", label: "Description", type: "textarea", required: false },
            ];

    const referenceDataMissing = (resource === "bills" && patients.length === 0)
      || (resource === "appointments" && (patients.length === 0 || doctors.length === 0));

    return (
      <>
        <RecordDialog
          title={`New ${resource.slice(0, -1)} record`}
          resource={resource}
          fields={fields}
          onClose={onClose}
          onSaved={onSaved}
        />
        {error && <p className="fixed bottom-6 left-1/2 z-[60] -translate-x-1/2 rounded-lg bg-rose-700 px-4 py-3 text-sm text-white" role="alert">{error}</p>}
        {referenceDataMissing && (
          <p className="fixed bottom-6 left-1/2 z-[60] -translate-x-1/2 rounded-lg bg-amber-100 px-4 py-3 text-sm text-amber-900" role="status">
            {resource === "appointments" ? "Add at least one patient and doctor first." : "Add at least one patient first."}
          </p>
        )}
      </>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" role="presentation">
      <section aria-labelledby="new-record-title" aria-modal="true" className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-2xl" role="dialog">
        <div className="mb-5 flex items-start justify-between gap-4">
          <h2 className="text-xl font-semibold text-slate-900" id="new-record-title">Choose a record type</h2>
          <button aria-label="Close form" className="text-slate-500 hover:text-slate-900" onClick={onClose} type="button">Close</button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {(role === "Admin" ? ["patients", "doctors", "appointments", "bills"] as Resource[] : ["appointments"] as Resource[]).map((type) => (
            <button key={type} className="rounded-lg border border-slate-200 px-4 py-3 text-left font-medium capitalize text-slate-800 hover:border-sky-500 hover:bg-sky-50" onClick={() => setResource(type)} type="button">
              {type.slice(0, -1)}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
