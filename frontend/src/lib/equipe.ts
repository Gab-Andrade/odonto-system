import { useQuery } from "@tanstack/react-query";

import { api, ok } from "../api/client";

/** Membros ativos da clínica (nome e papel), usados para escolher dentista. */
export function useEquipe() {
  return useQuery({
    queryKey: ["equipe"],
    queryFn: async () => ok(await api.GET("/auth/equipe")),
    staleTime: 5 * 60_000,
  });
}

export function useDentistas() {
  const equipe = useEquipe();
  return {
    ...equipe,
    data: equipe.data?.filter((m) => m.role === "dentista" || m.role === "admin"),
  };
}

export function nomeMembro(
  equipe: { user_id: string; full_name: string }[] | undefined,
  id?: string | null,
): string {
  if (!id) return "—";
  return equipe?.find((m) => m.user_id === id)?.full_name ?? "—";
}
