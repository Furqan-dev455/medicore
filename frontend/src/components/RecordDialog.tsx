"use client";

import { FormEvent, useState } from "react";
import { writeJson } from "@/data/hospitalApi";

export type RecordField = {
  name: string;
  label: string;
  type?: "text" | "email" | "number" | "date" | "time" | "select" | "textarea";
  required?: boolean;
  min?: string;
  step?: string;
  options?: Array<{ value: string | number; label: string }>;
};

type RecordDialogProps = {
  title: string;
  resource: string;
  fields: RecordField[];
  initialValue?: Record<string, string | number | null | undefined>;
  onClose: () => void;
  onSaved: () => Promise<void>;
};

export function RecordDialog({
  title,
  resource,
  fields,
  initialValue,
  onClose,
  onSaved,
}: RecordDialogProps) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      fields.map((field) => [field.name, String(initialValue?.[field.name] ?? "")]),
    ),
  );
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");

    try {
      const id = initialValue?.id;
      await writeJson(
        id ? `/api/${resource}/${id}` : `/api/${resource}`,
        id ? "PUT" : "POST",
        values,
      );
      await onSaved();
      onClose();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to save record.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4" role="presentation">
      <section
        aria-labelledby="record-dialog-title"
        aria-modal="true"
        className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-xl border border-slate-200 bg-white p-6 shadow-2xl"
        role="dialog"
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <h2 className="text-xl font-semibold text-slate-900" id="record-dialog-title">{title}</h2>
          <button aria-label="Close form" className="text-slate-500 hover:text-slate-900" onClick={onClose} type="button">Close</button>
        </div>
        <form className="space-y-4" onSubmit={submit}>
          {fields.map((field) => {
            const commonProps = {
              id: field.name,
              name: field.name,
              required: field.required ?? true,
              value: values[field.name] ?? "",
              onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
                setValues((current) => ({ ...current, [field.name]: event.target.value })),
              className: "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-sky-600 focus:ring-2 focus:ring-sky-100",
            };

            return (
              <div key={field.name}>
                <label className="mb-1.5 block text-sm font-medium text-slate-700" htmlFor={field.name}>{field.label}</label>
                {field.type === "select" ? (
                  <select {...commonProps}>
                    <option value="">Select {field.label.toLowerCase()}</option>
                    {field.options?.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                ) : field.type === "textarea" ? (
                  <textarea {...commonProps} rows={3} />
                ) : (
                  <input {...commonProps} min={field.min} step={field.step} type={field.type ?? "text"} />
                )}
              </div>
            );
          })}
          {error && <p className="text-sm text-rose-700" role="alert">{error}</p>}
          <div className="flex justify-end gap-3 border-t border-slate-200 pt-4">
            <button className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50" onClick={onClose} type="button">Cancel</button>
            <button className="rounded-md bg-sky-700 px-4 py-2 text-sm font-medium text-white hover:bg-sky-600 disabled:cursor-wait disabled:opacity-60" disabled={saving} type="submit">
              {saving ? "Saving..." : "Save record"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
