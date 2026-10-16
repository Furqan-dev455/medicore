"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { fetchJson, writeJson } from "@/data/hospitalApi";

type Role = "Admin" | "Doctor" | "Patient" | "Receptionist" | "Unassigned";
type ProfileOption = { id: number; name: string; user_id: number | null };
type ManagedUser = {
  id: number;
  username: string;
  email: string;
  role: Role;
  is_active: boolean;
  is_superuser: boolean;
  doctor_profile_id: number | null;
  patient_profile_id: number | null;
};
type Draft = { role: Role; profile_id: string };
type UsersResponse = {
  current_user_id: number;
  users: ManagedUser[];
  doctor_profiles: ProfileOption[];
  patient_profiles: ProfileOption[];
};

const roles: Role[] = ["Admin", "Doctor", "Patient", "Receptionist", "Unassigned"];

export default function UserRolesPage() {
  const router = useRouter();
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [doctorProfiles, setDoctorProfiles] = useState<ProfileOption[]>([]);
  const [patientProfiles, setPatientProfiles] = useState<ProfileOption[]>([]);
  const [currentUserId, setCurrentUserId] = useState<number | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadUsers = useCallback(async () => {
    const data = await fetchJson<UsersResponse>("/api/users/");
    setUsers(data.users);
    setCurrentUserId(data.current_user_id);
    setDoctorProfiles(data.doctor_profiles);
    setPatientProfiles(data.patient_profiles);
    setDrafts(Object.fromEntries(data.users.map((user) => [user.id, {
      role: user.role,
      profile_id: user.role === "Doctor"
        ? String(user.doctor_profile_id ?? "")
        : user.role === "Patient" ? String(user.patient_profile_id ?? "") : "",
    }])));
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadUsers()
        .catch((loadError) => setError(loadError instanceof Error ? loadError.message : "Unable to load users."))
        .finally(() => setLoading(false));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadUsers]);

  async function saveUserRole(user: ManagedUser) {
    const draft = drafts[user.id] ?? { role: user.role, profile_id: "" };
    const profileId = draft.profile_id ? Number(draft.profile_id) : null;
    const originalProfileId = draft.role === "Doctor"
      ? user.doctor_profile_id
      : draft.role === "Patient" ? user.patient_profile_id : null;
    if (draft.role === user.role && profileId === originalProfileId) return;

    setSavingId(user.id);
    setError("");
    setNotice("");
    try {
      await writeJson(`/api/users/${user.id}/role`, "POST", {
        role: draft.role,
        profile_id: profileId,
      });
      if (user.id === currentUserId) {
        router.push("/");
        return;
      }
      await loadUsers();
      setNotice(`${user.username}'s role and profile were updated.`);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to update this user.");
    } finally {
      setSavingId(null);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <header>
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-sky-600">Administration</p>
          <h2 className="mt-2 text-3xl font-bold text-slate-900">User roles</h2>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Assign one portal role to each account. Doctor and Patient accounts need a linked profile to access their own records.
          </p>
        </header>

        {error && <p className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800" role="alert">{error}</p>}
        {notice && <p className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800" role="status">{notice}</p>}

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {loading ? (
            <p className="p-6 text-sm text-slate-500">Loading users...</p>
          ) : users.length === 0 ? (
            <p className="p-6 text-sm text-slate-500">No user accounts found.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px] text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-5 py-4 font-semibold">Username</th>
                    <th className="px-5 py-4 font-semibold">Email</th>
                    <th className="px-5 py-4 font-semibold">Status</th>
                    <th className="px-5 py-4 font-semibold">Portal role</th>
                    <th className="px-5 py-4 font-semibold">Linked profile</th>
                    <th className="px-5 py-4 font-semibold">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {users.map((user) => {
                    const draft = drafts[user.id] ?? { role: user.role, profile_id: "" };
                    const profiles = draft.role === "Doctor"
                      ? doctorProfiles
                      : draft.role === "Patient" ? patientProfiles : [];
                    const selectedProfileId = draft.profile_id;
                    const changed = draft.role !== user.role ||
                      (draft.role === "Doctor" && Number(selectedProfileId || 0) !== (user.doctor_profile_id ?? 0)) ||
                      (draft.role === "Patient" && Number(selectedProfileId || 0) !== (user.patient_profile_id ?? 0));

                    return (
                      <tr key={user.id}>
                        <td className="px-5 py-4 font-medium text-slate-900">
                          {user.username}{user.id === currentUserId ? <span className="ml-2 text-xs text-slate-500">(you)</span> : null}
                          {user.is_superuser ? <span className="ml-2 text-xs text-sky-700">(superuser)</span> : null}
                        </td>
                        <td className="px-5 py-4 text-slate-600">{user.email || "—"}</td>
                        <td className="px-5 py-4">
                          <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${user.is_active ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>
                            {user.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td className="px-5 py-4">
                          <select
                            aria-label={`Role for ${user.username}`}
                            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-800 disabled:bg-slate-100 disabled:text-slate-500"
                            disabled={user.is_superuser || savingId === user.id}
                            value={draft.role}
                            onChange={(event) => {
                              const role = event.target.value as Role;
                              const profileId = role === "Doctor"
                                ? user.doctor_profile_id
                                : role === "Patient" ? user.patient_profile_id : null;
                              setDrafts((current) => ({
                                ...current,
                                [user.id]: { role, profile_id: String(profileId ?? "") },
                              }));
                            }}
                          >
                            {roles.map((role) => <option key={role} value={role}>{role}</option>)}
                          </select>
                        </td>
                        <td className="px-5 py-4">
                          {profiles.length > 0 ? (
                            <select
                              aria-label={`Linked profile for ${user.username}`}
                              className="max-w-64 rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-800 disabled:bg-slate-100 disabled:text-slate-500"
                              disabled={user.is_superuser || savingId === user.id}
                              value={selectedProfileId}
                              onChange={(event) => setDrafts((current) => ({
                                ...current,
                                [user.id]: { ...draft, profile_id: event.target.value },
                              }))}
                            >
                              <option value="">No profile linked</option>
                              {profiles.map((profile) => (
                                <option
                                  key={profile.id}
                                  disabled={profile.user_id !== null && profile.user_id !== user.id}
                                  value={profile.id}
                                >
                                  {profile.name}{profile.user_id !== null && profile.user_id !== user.id ? " (already linked)" : ""}
                                </option>
                              ))}
                            </select>
                          ) : draft.role === "Doctor" || draft.role === "Patient" ? (
                            <span className="text-sm text-slate-500">No profiles available</span>
                          ) : (
                            <span className="text-sm text-slate-400">—</span>
                          )}
                        </td>
                        <td className="px-5 py-4">
                          <button
                            className="rounded-lg bg-sky-700 px-3 py-2 font-medium text-white hover:bg-sky-600 disabled:cursor-not-allowed disabled:bg-slate-300"
                            disabled={!changed || user.is_superuser || savingId === user.id}
                            onClick={() => void saveUserRole(user)}
                            type="button"
                          >
                            {savingId === user.id ? "Saving..." : "Save"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
