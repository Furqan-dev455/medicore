"use client";

import { FormEvent, useState } from "react";
import { BillApi, writeJson } from "@/data/hospitalApi";

type PatientCheckoutDialogProps = {
  bill: BillApi;
  onClose: () => void;
};

const formatMoney = (amount: number) => `Rs. ${amount.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function PatientCheckoutDialog({ bill, onClose }: PatientCheckoutDialogProps) {
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const formData = new FormData(event.currentTarget);

    try {
      const result = await writeJson<{ checkout_url: string }>(`/api/bills/${bill.id}/checkout`, "POST", {
        amount: formData.get("amount"),
      });
      window.location.assign(result.checkout_url);
    } catch (checkoutError) {
      setError(checkoutError instanceof Error ? checkoutError.message : "Unable to start secure checkout.");
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" role="presentation">
      <section aria-labelledby="checkout-dialog-title" aria-modal="true" className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-2xl" role="dialog">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-slate-900" id="checkout-dialog-title">Pay bill securely</h2>
            <p className="mt-1 text-sm text-slate-500">Bill #{bill.id}</p>
          </div>
          <button aria-label="Close checkout form" className="text-slate-500 hover:text-slate-900" disabled={saving} onClick={onClose} type="button">Close</button>
        </div>
        <div className="mb-5 rounded-lg bg-slate-50 p-4 text-sm">
          <div className="flex justify-between"><span className="text-slate-600">Bill total</span><span className="font-medium">{formatMoney(bill.total)}</span></div>
          <div className="mt-2 flex justify-between"><span className="text-slate-600">Remaining balance</span><span className="font-semibold text-slate-900">{formatMoney(bill.balance)}</span></div>
        </div>
        <form className="space-y-4" onSubmit={submit}>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700" htmlFor="checkout-amount">Payment amount</label>
            <input autoFocus id="checkout-amount" name="amount" type="number" min="0.01" max={bill.balance} step="0.01" defaultValue={bill.balance.toFixed(2)} required className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-sky-600 focus:ring-2 focus:ring-sky-100" />
            <p className="mt-1 text-xs text-slate-500">Pay all or part of the balance. Your bill changes after the gateway confirms payment.</p>
          </div>
          {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}
          <div className="flex justify-end gap-3 border-t border-slate-200 pt-4">
            <button className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50" disabled={saving} onClick={onClose} type="button">Cancel</button>
            <button className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-600 disabled:cursor-wait disabled:opacity-60" disabled={saving} type="submit">
              {saving ? "Opening checkout..." : "Continue to payment"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
