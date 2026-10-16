"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { writeJson } from "@/data/hospitalApi";

export default function ForgotPasswordPage() {
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setMessage("");
    const formData = new FormData(event.currentTarget);

    try {
      const result = await writeJson<{ message: string }>("/api/auth/password-reset", "POST", {
        email: formData.get("email"),
      });
      setMessage(result.message);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to request a reset link.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-7">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-sky-600">MediCore</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">Reset password</h1>
        </div>
        <form className="space-y-5" method="post" onSubmit={submit}>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="email">Account email</label>
            <input autoComplete="email" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-sky-500 focus:bg-white" id="email" name="email" required type="email" />
          </div>
          {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}
          {message && <p className="text-sm text-emerald-700" role="status">{message}</p>}
          <button className="w-full rounded-xl bg-sky-600 px-4 py-3 font-medium text-white transition hover:bg-sky-500 disabled:cursor-wait disabled:opacity-60" disabled={submitting} type="submit">
            {submitting ? "Sending..." : "Send reset link"}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-slate-500">
          <Link className="font-medium text-sky-700" href="/login">Back to sign in</Link>
        </p>
      </div>
    </main>
  );
}
