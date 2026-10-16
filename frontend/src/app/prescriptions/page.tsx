"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { usePortalRole } from "@/components/usePortalRole";
import { fetchAuthenticatedJson, PatientApi, writeJson } from "@/data/hospitalApi";

type Medication = {
  id: number;
  name: string;
  strength: string;
  dosage_form: string;
  unit: string;
  stock_quantity: number;
  low_stock: boolean;
};

type Prescription = {
  id: number;
  patient: string;
  doctor: string;
  date: string;
  notes: string;
  items: Array<{ medication: string; quantity: number; unit: string; dosage: string; duration: string; instructions: string }>;
};

type DraftItem = { medication_id: string; quantity: string; dosage: string; duration: string; instructions: string };
const emptyItem = (): DraftItem => ({ medication_id: "", quantity: "1", dosage: "", duration: "", instructions: "" });

export default function PrescriptionsPage() {
  const role = usePortalRole();
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [patients, setPatients] = useState<PatientApi[]>([]);
  const [medications, setMedications] = useState<Medication[]>([]);
  const [inventoryLoaded, setInventoryLoaded] = useState(false);
  const [patientId, setPatientId] = useState("");
  const [items, setItems] = useState<DraftItem[]>([emptyItem()]);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    const prescriptionResult = await fetchAuthenticatedJson<{ prescriptions: Prescription[] }>("/api/prescriptions/");
    setPrescriptions(prescriptionResult.prescriptions);
    if (role === "Doctor") {
      const [patientResult, medicationResult] = await Promise.all([
        fetchAuthenticatedJson<{ patients: PatientApi[] }>("/api/patients/"),
        fetchAuthenticatedJson<{ medications: Medication[] }>("/api/inventory/"),
      ]);
      setPatients(patientResult.patients);
      setMedications(medicationResult.medications);
      setInventoryLoaded(true);
    }
  }, [role]);

  async function refreshInventory() {
    setError("");
    try {
      const result = await fetchAuthenticatedJson<{ medications: Medication[] }>("/api/inventory/");
      setMedications(result.medications);
      setInventoryLoaded(true);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load pharmacy inventory.");
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadData().catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Unable to load prescriptions."));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadData]);

  function updateItem(index: number, key: keyof DraftItem, value: string) {
    setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await writeJson("/api/prescriptions/", "POST", {
        patient_id: patientId,
        notes,
        items: items.map((item) => ({
          ...item,
          medication_id: Number(item.medication_id),
          quantity: Number(item.quantity),
        })),
      });
      setItems([emptyItem()]);
      setPatientId("");
      setNotes("");
      await loadData();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save prescription.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <header>
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-600">Clinical care</p>
          <h2 className="mt-2 text-3xl font-bold text-slate-900">Prescriptions</h2>
        </header>

        {error && <p className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert">{error}</p>}

        {role === "Doctor" && <form className="space-y-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" onSubmit={submit}>
          <h3 className="text-lg font-semibold text-slate-900">Write a prescription</h3>
          <label className="block text-sm font-medium text-slate-700">
            Patient
            <select required value={patientId} onChange={(event) => setPatientId(event.target.value)} className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2">
              <option value="">Select a patient</option>
              {patients.map((patient) => <option key={patient.id} value={patient.id}>{patient.name}</option>)}
            </select>
          </label>

          <div className="space-y-4">
            {items.map((item, index) => <fieldset key={index} className="grid gap-3 rounded-lg border border-slate-200 p-4 md:grid-cols-2">
              <legend className="px-1 text-sm font-medium text-slate-700">Medicine {index + 1}</legend>
              <label className="text-sm text-slate-700">Medicine
                <select required value={item.medication_id} onChange={(event) => updateItem(index, "medication_id", event.target.value)} className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2">
                  <option value="">Select medicine</option>
                  {medications.map((medicine) => <option key={medicine.id} value={medicine.id} disabled={medicine.stock_quantity === 0}>
                    {[medicine.name, medicine.strength, medicine.dosage_form].filter(Boolean).join(" · ")} — {medicine.stock_quantity} {medicine.unit} available
                  </option>)}
                </select>
              </label>
              <label className="text-sm text-slate-700">Quantity to dispense
                <input required min="1" step="1" type="number" value={item.quantity} onChange={(event) => updateItem(index, "quantity", event.target.value)} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2" />
              </label>
              <label className="text-sm text-slate-700">Dosage
                <input required maxLength={120} placeholder="e.g. 1 tablet twice daily" value={item.dosage} onChange={(event) => updateItem(index, "dosage", event.target.value)} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2" />
              </label>
              <label className="text-sm text-slate-700">Duration
                <input maxLength={120} placeholder="e.g. 7 days" value={item.duration} onChange={(event) => updateItem(index, "duration", event.target.value)} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2" />
              </label>
              <label className="text-sm text-slate-700">Instructions
                <input maxLength={300} placeholder="e.g. Take after food" value={item.instructions} onChange={(event) => updateItem(index, "instructions", event.target.value)} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2" />
              </label>
              {items.length > 1 && <button type="button" onClick={() => setItems((current) => current.filter((_, itemIndex) => itemIndex !== index))} className="justify-self-start text-sm text-rose-700">Remove medicine</button>}
            </fieldset>)}
          </div>
          {inventoryLoaded && medications.length === 0 && <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" role="status">
            No active medicines are in pharmacy inventory, so the dropdown is empty. Ask an administrator to add the hospital’s medicines and current stock in <Link className="font-semibold underline" href="/pharmacy">Pharmacy inventory</Link>.
            <button className="ml-2 font-semibold underline" onClick={() => void refreshInventory()} type="button">Refresh list</button>
          </div>}
          {!inventoryLoaded && <p className="text-sm text-slate-500" role="status">Loading pharmacy medicines...</p>}
          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={() => setItems((current) => [...current, emptyItem()])} disabled={items.length >= 30} className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50">Add medicine</button>
          </div>
          <label className="block text-sm font-medium text-slate-700">Prescription notes
            <textarea maxLength={4000} rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2" />
          </label>
          <button disabled={saving} className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{saving ? "Saving and dispensing..." : "Save prescription and dispense"}</button>
          <p className="text-xs text-slate-500">Saving reserves and deducts all selected quantities atomically from pharmacy stock.</p>
        </form>}

        <section className="space-y-4">
          <h3 className="text-lg font-semibold text-slate-900">Prescription history</h3>
          {prescriptions.length === 0 && <p className="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-500">No prescriptions found.</p>}
          {prescriptions.map((prescription) => <article key={prescription.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap justify-between gap-2">
              <div><h4 className="font-semibold text-slate-900">{prescription.patient}</h4><p className="text-sm text-slate-500">{prescription.doctor} · {new Date(prescription.date).toLocaleString()}</p></div>
              <span className="text-sm text-slate-500">Prescription #{prescription.id}</span>
            </div>
            <ul className="mt-4 space-y-2 text-sm text-slate-700">
              {prescription.items.map((item, index) => <li key={`${prescription.id}-${index}`} className="rounded-md bg-slate-50 p-3">
                <strong>{item.medication}</strong> · {item.quantity} {item.unit}<br />{item.dosage}{item.duration ? ` · ${item.duration}` : ""}{item.instructions ? ` · ${item.instructions}` : ""}
              </li>)}
            </ul>
            {prescription.notes && <p className="mt-3 text-sm text-slate-600">{prescription.notes}</p>}
          </article>)}
        </section>
      </div>
    </AppShell>
  );
}
