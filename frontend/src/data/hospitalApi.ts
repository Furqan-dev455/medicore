export type DashboardStat = {
  label: string;
  value: number | string;
  change: string;
  tone: "emerald" | "blue" | "violet" | "amber";
};

export type DashboardData = {
  role?: "Admin" | "Doctor" | "Patient" | "Receptionist" | "Demo" | "Unassigned";
  stats: DashboardStat[];
  recent_appointments: Array<{
    id: number;
    patient: string;
    doctor: string;
    date: string;
    time: string;
    status: string;
  }>;
  bills: Array<{
    id: number;
    patient: string;
    total: number;
    paid: number;
    balance: number;
    status: string;
  }>;
};

export type PatientApi = {
  id: number;
  name: string;
  age: number;
  gender: string;
  phone: string;
  address: string;
  medical_history: string;
  status: string;
};

export type DoctorApi = {
  id: number;
  name: string;
  specialization: string;
  phone: string;
  email: string;
};

export type AppointmentApi = {
  id: number;
  patient_id: number;
  doctor_id: number;
  patient: string;
  doctor: string;
  date: string;
  time: string;
  status: string;
  notes: string;
};

export type BillApi = {
  id: number;
  patient_id: number;
  patient: string;
  total: number;
  total_amount: string;
  description: string;
  paid: number;
  balance: number;
  status: string;
  invoice_status: "pending" | "processing" | "ready" | "failed";
};

export class ApiError extends Error {
  constructor(public readonly status: number) {
    super(`Request failed: ${status}`);
    this.name = "ApiError";
  }
}

// Use Next's same-origin /api rewrite by default. Calling Django directly at
// 127.0.0.1 from a localhost frontend makes the session cookie cross-site and
// the browser drops it on the next request.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

function toApiUrl(url: string): string {
  const normalizedUrl = url.replace(/\/+$/, "") || "/";
  if (normalizedUrl.startsWith("http://") || normalizedUrl.startsWith("https://")) {
    return normalizedUrl;
  }
  return `${API_BASE}${normalizedUrl}`;
}

export async function fetchJson<T>(url: string): Promise<T> {
  const normalizedUrl = toApiUrl(url);
  const response = await fetch(normalizedUrl, { cache: "no-store", credentials: "include" });

  if (!response.ok) {
    throw new ApiError(response.status);
  }

  return response.json() as Promise<T>;
}

export async function fetchAuthenticatedJson<T>(url: string): Promise<T> {
  const isDemo = typeof window !== "undefined" && (
    window.location.pathname === "/demo"
    ||
    new URLSearchParams(window.location.search).get("demo") === "1"
    || (() => {
      try {
        return window.sessionStorage.getItem("medicore-demo-session") === "true";
      } catch {
        return false;
      }
    })()
  );
  if (isDemo) {
    if (url === "/api/dashboard/") {
      const { appointments, bills, stats } = await import("@/data/mockData");
      return {
        stats: stats.map((stat) => ({ ...stat, value: stat.value.replace(/,/g, "") })),
        recent_appointments: appointments.map((item) => ({ ...item, id: item.id })),
        bills: bills.map((bill) => ({ ...bill, balance: bill.balance })),
      } as T;
    }
    throw new ApiError(404);
  }
  const session = await fetchJson<{ authenticated: boolean }>("/api/auth/session");
  if (!session.authenticated) throw new ApiError(401);
  return fetchJson<T>(url);
}

async function getCsrfToken(): Promise<string> {
  const response = await fetch(toApiUrl("/api/csrf"), { cache: "no-store", credentials: "include" });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error ?? `Request failed: ${response.status}`);
  if (!data || typeof data.csrfToken !== "string") throw new Error("The server did not provide a CSRF token. Refresh and try again.");
  return data.csrfToken as string;
}

export async function writeJson<T>(url: string, method: "POST" | "PUT", payload: unknown): Promise<T> {
  const csrfToken = await getCsrfToken();
  const normalizedUrl = toApiUrl(url);
  const response = await fetch(normalizedUrl, {
    method,
    cache: "no-store",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
    body: JSON.stringify(payload),
  });
  const data: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    if (!data || typeof data !== "object") {
      // Django's debug error page is HTML, so avoid surfacing its contents in
      // the UI. Include the API path to make matching the failure to the
      // backend traceback straightforward.
      const path = new URL(normalizedUrl, window.location.href).pathname;
      throw new Error(`Request failed: ${response.status} (${method} ${path}). The server returned a non-JSON response.`);
    }
    const errorData = data as { errors?: Record<string, string[]>; error?: string };
    const fieldErrors = errorData.errors
      ? Object.values(errorData.errors).flat().join(" ")
      : "";
    throw new Error(fieldErrors || errorData.error || `Request failed: ${response.status}`);
  }

  if (!data) throw new Error("The server returned an invalid response.");
  return data as T;
}
