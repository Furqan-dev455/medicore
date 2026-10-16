"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { usePortalRole } from "@/components/usePortalRole";
import { PaymentDialog } from "@/components/PaymentDialog";
import { RecordDialog, RecordField } from "@/components/RecordDialog";
import { BillApi, fetchAuthenticatedJson, PatientApi } from "@/data/hospitalApi";

export default function BillsPage() {
  const role = usePortalRole();
  const [bills, setBills] = useState<BillApi[]>([]);
  const [patients, setPatients] = useState<PatientApi[]>([]);
  const [editing, setEditing] = useState<BillApi | null>(null);
  const [paying, setPaying] = useState<BillApi | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [error, setError] = useState("");
  const [invoiceMessage, setInvoiceMessage] = useState("");

  const fields: RecordField[] = [
    { name: "patient", label: "Patient", type: "select", options: patients.map((patient) => ({ value: patient.id, label: patient.name })) },
    { name: "total_amount", label: "Total amount", type: "number", min: "0.01", step: "0.01" },
    { name: "description", label: "Description", type: "textarea", required: false },
  ];
  const formatMoney = (amount: number) => `Rs. ${amount.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  async function loadData() {
    const [billData, patientData] = await Promise.all([
      fetchAuthenticatedJson<{ bills: BillApi[] }>("/api/bills/"),
      fetchAuthenticatedJson<{ patients: PatientApi[] }>("/api/patients/"),
    ]);
    setBills(billData.bills);
    setPatients(patientData.patients);
  }

  useEffect(() => {
    Promise.all([
      fetchAuthenticatedJson<{ bills: BillApi[] }>("/api/bills/"),
      fetchAuthenticatedJson<{ patients: PatientApi[] }>("/api/patients/"),
    ])
      .then(([billData, patientData]) => {
        setBills(billData.bills);
        setPatients(patientData.patients);
      })
      .catch((loadError) => setError(loadError.message));
  }, []);

  useEffect(() => {
    if (!bills.some((bill) => bill.invoice_status === "processing")) return;
    const timer = window.setInterval(() => {
      fetchAuthenticatedJson<{ bills: BillApi[] }>("/api/bills/")
        .then((data) => setBills(data.bills))
        .catch((loadError) => setError(loadError.message));
    }, 3000);
    return () => window.clearInterval(timer);
  }, [bills]);

  async function downloadInvoice(bill: BillApi) {
    setInvoiceMessage("");
    try {
      const response = await fetch(`/api/bills/${bill.id}/invoice`, { credentials: "include" });
      if (response.status === 202) {
        setInvoiceMessage("The invoice is still being prepared. It will be ready shortly.");
        return;
      }
      if (!response.ok) throw new Error(`Unable to download invoice (${response.status}).`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `MediCore-invoice-${bill.id}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (downloadError) {
      setInvoiceMessage(downloadError instanceof Error ? downloadError.message : "Unable to download invoice.");
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <header className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-600">Finance</p>
            <h2 className="mt-2 text-3xl font-bold text-slate-900">Bills</h2>
          </div>
          {role === "Admin" && <button className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-600" onClick={() => { setEditing(null); setDialogOpen(true); }}>Create bill</button>}
        </header>

        {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}
        {invoiceMessage && <p className="text-sm text-sky-800" role="status">{invoiceMessage}</p>}
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50 text-left text-sm text-slate-600">
              <tr>
                <th className="px-5 py-4 font-medium">Patient</th>
                <th className="px-5 py-4 font-medium">Total</th>
                <th className="px-5 py-4 font-medium">Paid</th>
                <th className="px-5 py-4 font-medium">Balance</th>
                <th className="px-5 py-4 font-medium">Status</th>
                <th className="px-5 py-4 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-sm text-slate-700">
              {bills.map((bill) => (
                <tr key={bill.id} className="hover:bg-slate-50">
                  <td className="px-5 py-4 font-medium text-slate-900">{bill.patient}</td>
                  <td className="px-5 py-4">{formatMoney(bill.total)}</td>
                  <td className="px-5 py-4">{formatMoney(bill.paid)}</td>
                  <td className="px-5 py-4">{formatMoney(bill.balance)}</td>
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
                  <td className="px-5 py-4">
                    <div className="flex flex-wrap gap-3">
                      {role === "Admin" && bill.status !== "Paid" && <button className="font-medium text-emerald-700 hover:text-emerald-900" onClick={() => setPaying(bill)}>Record payment</button>}
                      <button className="font-medium text-sky-700 hover:text-sky-900 disabled:text-slate-400" disabled={bill.invoice_status !== "ready"} onClick={() => downloadInvoice(bill)} type="button">
                        {bill.invoice_status === "processing" ? "Preparing invoice…" : bill.invoice_status === "failed" ? "Invoice unavailable" : "Invoice PDF"}
                      </button>
                      {role === "Admin" && <button className="font-medium text-slate-700 hover:text-slate-900" onClick={() => { setEditing(bill); setDialogOpen(true); }}>Edit</button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {dialogOpen && <RecordDialog
        title={editing ? "Edit bill" : "Create bill"}
        resource="bills"
        fields={fields}
        initialValue={editing ? {
          id: editing.id,
          patient: editing.patient_id,
          total_amount: editing.total_amount,
          description: editing.description,
        } : undefined}
        onClose={() => setDialogOpen(false)}
        onSaved={loadData}
      />}
      {paying && <PaymentDialog bill={paying} onClose={() => setPaying(null)} onSaved={loadData} />}
    </AppShell>
  );
}
