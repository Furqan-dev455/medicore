"use client";

import { FormEvent, useState } from "react";
import { BillApi, writeJson } from "@/data/hospitalApi";

type PaymentDialogProps = {
  bill: BillApi;
  onClose: () => void;
  onSaved: () => Promise<void>;
};

const formatMoney = (amount: number) => `Rs. ${amount.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function PaymentDialog({ bill, onClose, onSaved }: PaymentDialogProps) {
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const formData = new FormData(event.currentTarget);

    try {
      await writeJson(`/api/bills/${bill.id}/payments`, "POST", {
        amount: formData.get("amount"),
        payment_method: formData.get("payment_method"),
      });
      await onSaved();
      onClose();
    } catch (paymentError) {
      setError(paymentError instanceof Error ? paymentError.message : "Unable to record payment.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" role="presentation">
      <section aria-labelledby="payment-dialog-title" aria-modal="true" className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-2xl" role="dialog">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-slate-900" id="payment-dialog-title">Record payment</h2>
            <p className="mt-1 text-sm text-slate-500">{bill.patient} · Bill #{bill.id}</p>
          </div>
          <button aria-label="Close payment form" className="text-slate-500 hover:text-slate-900" onClick={onClose} type="button">Close</button>
        </div>
        <div className="mb-5 rounded-lg bg-slate-50 p-4 text-sm">
          <div className="flex justify-between"><span className="text-slate-600">Bill total</span><span className="font-medium">{formatMoney(bill.total)}</span></div>
          <div className="mt-2 flex justify-between"><span className="text-slate-600">Remaining balance</span><span className="font-semibold text-slate-900">{formatMoney(bill.balance)}</span></div>
        </div>
        <form className="space-y-4" onSubmit={submit}>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700" htmlFor="payment-amount">Payment amount</label>
            <input autoFocus id="payment-amount" name="amount" type="number" min="0.01" max={bill.balance} step="0.01" defaultValue={bill.balance.toFixed(2)} required className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-sky-600 focus:ring-2 focus:ring-sky-100" />
            <p className="mt-1 text-xs text-slate-500">Enter a partial amount or the full remaining balance.</p>
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700" htmlFor="payment-method">Payment method</label>
            <select id="payment-method" name="payment_method" required defaultValue="Cash" className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-sky-600 focus:ring-2 focus:ring-sky-100">
              <option value="Cash">Cash</option>
              <option value="Card">Card</option>
              <option value="Bank Transfer">Bank transfer</option>
            </select>
          </div>
          {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}
          <div className="flex justify-end gap-3 border-t border-slate-200 pt-4">
            <button className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50" onClick={onClose} type="button">Cancel</button>
            <button className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-600 disabled:cursor-wait disabled:opacity-60" disabled={saving} type="submit">
              {saving ? "Recording..." : "Record payment"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
