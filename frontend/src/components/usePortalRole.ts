"use client";

import { useEffect, useState } from "react";
import type { PortalRole } from "@/components/AppShell";
import { fetchJson } from "@/data/hospitalApi";

export function usePortalRole() {
  const [role, setRole] = useState<PortalRole>("Unassigned");

  useEffect(() => {
    fetchJson<{ authenticated: boolean; role?: PortalRole }>("/api/auth/session")
      .then((session) => {
        setRole(session.authenticated ? session.role ?? "Unassigned" : "Unassigned");
      })
      .catch(() => setRole("Unassigned"));
  }, []);

  return role;
}
