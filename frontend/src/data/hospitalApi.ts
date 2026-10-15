export type DashboardStat = {
  label: string;
  value: number | string;
  change: string;
  tone: "emerald" | "blue" | "violet" | "amber";
};

export type DashboardData = {
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
  patient: string;
  doctor: string;
  date: string;
  time: string;
  status: string;
};

export type BillApi = {
  id: number;
  patient: string;
  total: number;
  paid: number;
  balance: number;
  status: string;
};

export async function fetchJson<T>(url: string): Promise<T> {
  const normalizedUrl = url.replace(/\/+$/, "") || "/";
  const response = await fetch(normalizedUrl, { cache: "no-store" });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}
