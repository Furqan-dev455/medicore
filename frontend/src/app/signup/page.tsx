"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { writeJson } from "@/data/hospitalApi";

export default function SignupPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    const formData = new FormData(event.currentTarget);
    const username = String(formData.get("username") ?? "").trim();

    try {
      await writeJson<{ username: string }>("/api/auth/signup", "POST", {
        username,
        email: formData.get("email"),
        password1: formData.get("password1"),
        password2: formData.get("password2"),
      });
      router.push("/login");
      return;
    } catch (signupError) {
      setError(signupError instanceof Error ? signupError.message : "Unable to create account.");
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-7">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-sky-600">MediCore</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">Create account</h1>
        </div>
        <form className="space-y-4" onSubmit={submit}>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="username">Username</label>
            <input autoComplete="username" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-sky-500 focus:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2" id="username" name="username" required />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="email">Email</label>
            <input autoComplete="email" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-sky-500 focus:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2" id="email" name="email" required type="email" />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="password1">Password</label>
            <input autoComplete="new-password" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-sky-500 focus:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2" id="password1" name="password1" required type="password" />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="password2">Confirm password</label>
            <input autoComplete="new-password" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none focus:border-sky-500 focus:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2" id="password2" name="password2" required type="password" />
          </div>
          {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}
          <button className="w-full rounded-xl bg-sky-600 px-4 py-3 font-medium text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2" disabled={submitting} type="submit">
            {submitting ? "Creating account..." : "Create account"}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-slate-500">
          Already registered? <Link className="font-medium text-sky-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2" href="/login">Sign in</Link>
        </p>
      </div>
    </main>
  );
}
