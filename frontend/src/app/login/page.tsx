import Link from "next/link";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
        <div className="mb-8">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-sky-600">MediCore</p>
          <h1 className="mt-2 text-3xl font-bold text-slate-900">Welcome back</h1>
        </div>

        <form className="space-y-5">
          <div>
            <label htmlFor="email" className="mb-2 block text-sm font-medium text-slate-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              defaultValue="admin@medicore.com"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none ring-0 transition focus:border-sky-500 focus:bg-white"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-2 block text-sm font-medium text-slate-700">
              Password
            </label>
            <input
              id="password"
              type="password"
              defaultValue="password123"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-slate-900 outline-none ring-0 transition focus:border-sky-500 focus:bg-white"
            />
          </div>

          <button
            type="submit"
            className="w-full rounded-xl bg-sky-600 px-4 py-3 font-medium text-white transition hover:bg-sky-500"
          >
            Sign in
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-500">
          Need an account? <Link href="/" className="font-medium text-sky-600">Go to dashboard</Link>
        </p>
      </div>
    </main>
  );
}
