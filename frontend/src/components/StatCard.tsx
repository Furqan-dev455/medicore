type StatCardProps = {
  label: string;
  value: string;
  change: string;
  tone: "emerald" | "blue" | "violet" | "amber";
};

const toneMap = {
  emerald: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
  amber: "bg-amber-50 text-amber-700 ring-amber-200",
};

export function StatCard({ label, value, change, tone }: StatCardProps) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${toneMap[tone]}`}>
        {change}
      </div>
      <p className="mt-4 text-sm text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-slate-900">{value}</p>
    </div>
  );
}
