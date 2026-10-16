"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { usePortalRole } from "@/components/usePortalRole";
import { fetchAuthenticatedJson, writeJson } from "@/data/hospitalApi";

type Medication = {
  id: number;
  name: string;
  strength: string;
  dosage_form: string;
  unit: string;
  stock_quantity: number;
  low_stock: boolean;
  low_stock_threshold?: number;
  is_active?: boolean;
};

type MedicationDraft = Omit<Medication, "id" | "low_stock">;
const blankMedication: MedicationDraft = {
  name: "", strength: "", dosage_form: "", unit: "units", stock_quantity: 0, low_stock_threshold: 0, is_active: true,
};

export default function PharmacyPage() {
  const role = usePortalRole();
  const [medications, setMedications] = useState<Medication[]>([]);
  const [draft, setDraft] = useState<MedicationDraft>(blankMedication);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const loadInventory = useCallback(async () => {
    const result = await fetchAuthenticatedJson<{ medications: Medication[] }>("/api/inventory/");
    setMedications(result.medications);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadInventory().catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Unable to load pharmacy inventory."));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadInventory]);

  function editMedicine(medicine: Medication) {
    setEditingId(medicine.id);
    setDraft({
      name: medicine.name,
      strength: medicine.strength,
      dosage_form: medicine.dosage_form,
      unit: medicine.unit,
      stock_quantity: medicine.stock_quantity,
      low_stock_threshold: medicine.low_stock_threshold ?? 0,
      is_active: medicine.is_active ?? true,
    });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await writeJson(editingId ? `/api/inventory/${editingId}` : "/api/inventory", editingId ? "PUT" : "POST", draft);
      setDraft(blankMedication);
      setEditingId(null);
      await loadInventory();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save medicine.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <header>
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-600">Pharmacy</p>
          <h2 className="mt-2 text-3xl font-bold text-slate-900">Inventory</h2>
        </header>
        {error && <p className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800" role="alert">{error}</p>}

        {role === "Admin" && <form className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm md:grid-cols-2" onSubmit={submit}>
          <h3 className="md:col-span-2 text-lg font-semibold text-slate-900">{editingId ? "Update medicine and stock" : "Add medicine to pharmacy"}</h3>
          <label className="text-sm text-slate-700">Medicine name<input required maxLength={160} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2" /></label>
          <label className="text-sm text-slate-700">Strength<input maxLength={80} placeholder="e.g. 500 mg" value={draft.strength} onChange={(event) => setDraft({ ...draft, strength: event.target.value })} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2" /></label>
          <label className="text-sm text-slate-700">Form<input maxLength={50} placeholder="e.g. Tablet" value={draft.dosage_form} onChange={(event) => setDraft({ ...draft, dosage_form: event.target.value })} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2" /></label>
          <label className="text-sm text-slate-700">Stock unit<input required maxLength={30} placeholder="e.g. tablets" value={draft.unit} onChange={(event) => setDraft({ ...draft, unit: event.target.value })} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2" /></label>
          <label className="text-sm text-slate-700">Current stock<input required min="0" step="1" type="number" value={draft.stock_quantity} onChange={(event) => setDraft({ ...draft, stock_quantity: Number(event.target.value) })} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2" /></label>
          <label className="text-sm text-slate-700">Low stock alert at<input required min="0" step="1" type="number" value={draft.low_stock_threshold} onChange={(event) => setDraft({ ...draft, low_stock_threshold: Number(event.target.value) })} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2" /></label>
          <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={draft.is_active} onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })} />Available for prescribing</label>
          <div className="flex gap-3 md:col-span-2">
            <button disabled={saving} className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{saving ? "Saving..." : editingId ? "Save inventory" : "Add medicine"}</button>
            {editingId !== null && <button type="button" onClick={() => { setEditingId(null); setDraft(blankMedication); }} className="rounded-md border border-slate-300 px-4 py-2 text-sm">Cancel</button>}
          </div>
        </form>}

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-slate-600"><tr>
              <th className="px-5 py-3 font-medium">Medicine</th><th className="px-5 py-3 font-medium">Form</th><th className="px-5 py-3 font-medium">Stock</th><th className="px-5 py-3 font-medium">Status</th>{role === "Admin" && <th className="px-5 py-3 font-medium">Action</th>}
            </tr></thead>
            <tbody className="divide-y divide-slate-200 text-slate-700">
              {medications.map((medicine) => <tr key={medicine.id}>
                <td className="px-5 py-4 font-medium text-slate-900">{medicine.name}{medicine.strength && ` · ${medicine.strength}`}</td>
                <td className="px-5 py-4">{medicine.dosage_form || "—"}</td>
                <td className="px-5 py-4">{medicine.stock_quantity} {medicine.unit}</td>
                <td className="px-5 py-4">{medicine.is_active === false ? "Inactive" : medicine.low_stock ? <span className="font-medium text-amber-700">Low stock</span> : "In stock"}</td>
                {role === "Admin" && <td className="px-5 py-4"><button type="button" onClick={() => editMedicine(medicine)} className="font-medium text-sky-700">Edit stock</button></td>}
              </tr>)}
              {medications.length === 0 && <tr><td className="px-5 py-6 text-slate-500" colSpan={role === "Admin" ? 5 : 4}>No medicine has been added to the pharmacy yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
