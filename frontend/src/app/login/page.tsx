"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { writeJson } from "@/data/hospitalApi";

// Only allow same-origin relative paths like "/patients/12".
// Rejects "//evil.com", "/\evil.com", and absolute URLs (open-redirect protection).
function getSafeRedirect(): string {
  const next = new URLSearchParams(window.location.search).get("next");
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return "/";
  }
  return next;
}

export default function LoginPage() {
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    setSubmitting(true);
    setError("");
    const formData = new FormData(event.currentTarget);

    try {
      await writeJson("/api/auth/login", "POST", {
        username: String(formData.get("username") ?? "").trim(),
        password: String(formData.get("password") ?? ""),
      });
      // Keep the button disabled while the browser navigates away.
      window.location.assign(getSafeRedirect());
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Unable to sign in.");
      setSubmitting(false);
    }
  }

  const focusRing =
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2";

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-8">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-sky-600">MediCore</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">Welcome back</h1>
        </div>

        <form className="space-y-5" onSubmit={submit} aria-busy={submitting}>
          <div>
            <label htmlFor="username" className="mb-2 block text-sm font-medium text-slate-700">
              Username
            </label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              required
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "login-error" : undefined}
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none ring-0 transition focus:border-sky-500 focus:bg-white aria-[invalid=true]:border-rose-400"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-2 block text-sm font-medium text-slate-700">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "login-error" : undefined}
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none ring-0 transition focus:border-sky-500 focus:bg-white aria-[invalid=true]:border-rose-400"
            />
          </div>

          {error && (
            <p id="login-error" className="text-sm text-rose-700" role="alert">
              {error}
            </p>
          )}

          <button
            disabled={submitting}
            type="submit"
            className={`w-full rounded-xl bg-sky-600 px-4 py-3 font-medium text-white transition hover:bg-sky-500 disabled:cursor-wait disabled:opacity-60 ${focusRing}`}
          >
            {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <div className="mt-6 flex items-center justify-between gap-4 text-sm">
          <Link className={`rounded font-medium text-sky-700 hover:text-sky-900 ${focusRing}`} href="/signup">
            Create account
          </Link>
          <Link className={`rounded font-medium text-sky-700 hover:text-sky-900 ${focusRing}`} href="/forgot-password">
            Forgot password?
          </Link>
        </div>
      </div>
    </main>
  );
}