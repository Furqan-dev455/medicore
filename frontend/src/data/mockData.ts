export type Stat = {
  label: string;
  value: string;
  change: string;
  tone: "emerald" | "blue" | "violet" | "amber";
};

export type Patient = {
  id: number;
  name: string;
  age: number;
  gender: string;
  phone: string;
  address: string;
  status: "Active" | "Follow Up" | "Discharged";
};

export type Doctor = {
  id: number;
  name: string;
  specialization: string;
  phone: string;
  email: string;
};

export type Appointment = {
  id: number;
  patient: string;
  doctor: string;
  date: string;
  time: string;
  status: "Scheduled" | "Completed" | "Cancelled";
};

export type Bill = {
  id: number;
  patient: string;
  total: number;
  paid: number;
  balance: number;
  status: "Paid" | "Partial" | "Unpaid";
};

export const stats: Stat[] = [
  { label: "Patients", value: "1,248", change: "+12.5%", tone: "emerald" },
  { label: "Doctors", value: "86", change: "+4.2%", tone: "blue" },
  { label: "Appointments", value: "342", change: "+8.1%", tone: "violet" },
  { label: "Outstanding", value: "$28,450", change: "-3.4%", tone: "amber" },
];

export const patients: Patient[] = [
  { id: 1, name: "Sarah Johnson", age: 32, gender: "Female", phone: "+1 415 555 0147", address: "Downtown, Seattle", status: "Active" },
  { id: 2, name: "Michael Chen", age: 45, gender: "Male", phone: "+1 415 555 0132", address: "Bellevue, WA", status: "Follow Up" },
  { id: 3, name: "Ava Martinez", age: 28, gender: "Female", phone: "+1 206 555 0128", address: "Redmond, WA", status: "Active" },
  { id: 4, name: "Daniel Brooks", age: 51, gender: "Male", phone: "+1 206 555 0109", address: "Kirkland, WA", status: "Discharged" },
];

export const doctors: Doctor[] = [
  { id: 1, name: "Dr. Emily Parker", specialization: "Cardiology", phone: "+1 206 555 1001", email: "emily.parker@medicore.com" },
  { id: 2, name: "Dr. Noah Green", specialization: "Orthopedics", phone: "+1 206 555 1002", email: "noah.green@medicore.com" },
  { id: 3, name: "Dr. Priya Shah", specialization: "Neurology", phone: "+1 206 555 1003", email: "priya.shah@medicore.com" },
  { id: 4, name: "Dr. Lucas White", specialization: "Pediatrics", phone: "+1 206 555 1004", email: "lucas.white@medicore.com" },
];

export const appointments: Appointment[] = [
  { id: 1, patient: "Sarah Johnson", doctor: "Dr. Emily Parker", date: "2026-10-16", time: "09:30 AM", status: "Scheduled" },
  { id: 2, patient: "Michael Chen", doctor: "Dr. Noah Green", date: "2026-10-16", time: "11:00 AM", status: "Completed" },
  { id: 3, patient: "Ava Martinez", doctor: "Dr. Priya Shah", date: "2026-10-17", time: "01:15 PM", status: "Scheduled" },
  { id: 4, patient: "Daniel Brooks", doctor: "Dr. Lucas White", date: "2026-10-18", time: "08:45 AM", status: "Cancelled" },
];

export const bills: Bill[] = [
  { id: 1, patient: "Sarah Johnson", total: 1250, paid: 1250, balance: 0, status: "Paid" },
  { id: 2, patient: "Michael Chen", total: 980, paid: 420, balance: 560, status: "Partial" },
  { id: 3, patient: "Ava Martinez", total: 660, paid: 0, balance: 660, status: "Unpaid" },
  { id: 4, patient: "Daniel Brooks", total: 1500, paid: 1500, balance: 0, status: "Paid" },
];
