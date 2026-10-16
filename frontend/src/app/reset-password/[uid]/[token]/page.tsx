"use client";

import Link from "next/link";
import { FormEvent, Suspense, useState } from "react";
import { useParams } from "next/navigation";
import { writeJson } from "@/data/hospitalApi";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<main className="flex min-h-screen items-center justify-center bg-slate-100 p-6"><p className="text-sm text-slate-500">Loading reset form...</p></main>}>
      <ResetPasswordForm />
    </Suspense>
  );
}

function ResetPasswordForm() {
  const { uid, token } = useParams<{ uid: string; token: string }>();
  const [error, setError] = useState("");
  const [complete, setComplete] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    const formData = new FormData(event.currentTarget);

    try {
      await writeJson("/api/auth/password-reset/confirm", "POST", {
        uid,
        token,
        password: formData.get("password"),
        password_confirm: formData.get("password_confirm"),
      });
      setComplete(true);
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : "Unable to reset password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-7">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-sky-600">MediCore</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">Choose a new password</h1>
        </div>
        {complete ? (
          <div className="space-y-4">
            <p className="text-sm text-emerald-700" role="status">Your password has been changed.</p>
            <Link className="inline-flex rounded-xl bg-sky-600 px-4 py-3 font-medium text-white hover:bg-sky-500" href="/login">Return to sign in</Link>
          </div>
        ) : (
          <form className="space-y-4" onSubmit={submit}>
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="password">New password</label>
              <input autoComplete="new-password" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-sky-500 focus:bg-white" id="password" name="password" required type="password" />
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="password_confirm">Confirm new password</label>
              <input autoComplete="new-password" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-sky-500 focus:bg-white" id="password_confirm" name="password_confirm" required type="password" />
            </div>
            {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}
            <button className="w-full rounded-xl bg-sky-600 px-4 py-3 font-medium text-white transition hover:bg-sky-500 disabled:cursor-wait disabled:opacity-60" disabled={submitting} type="submit">
              {submitting ? "Updating..." : "Update password"}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
