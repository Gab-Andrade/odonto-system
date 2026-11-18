import { useQuery } from "@tanstack/react-query";

import { api, ok } from "../api/client";

export interface Procedimento {
  codigo: string;
  descricao: string;
  categoria: string | null;
}

/**
 * Procedimentos das últimas versões publicadas das tabelas ativas (sugestões no plano).
 * O preço de verdade é resolvido pela API ao emitir (cadeia de prioridade).
 */
export function useProcedimentos(habilitado = true) {
  return useQuery({
    enabled: habilitado,
    queryKey: ["procedimentos"],
    staleTime: 5 * 60_000,
    queryFn: async () => {
      const tabelas = ok(await api.GET("/precificacao/tabelas")).filter((t) => t.status === "ativa");
      const mapa = new Map<string, Procedimento>();
      for (const t of tabelas) {
        const versoes = ok(
          await api.GET("/precificacao/tabelas/{table_id}/versoes", { params: { path: { table_id: t.id } } }),
        );
        const publicada = versoes
          .filter((v) => v.status === "publicada")
          .sort((a, b) => b.version - a.version)[0];
        if (!publicada) continue;
        const itens = ok(
          await api.GET("/precificacao/tabelas/{table_id}/versoes/{version_id}/itens", {
            params: { path: { table_id: t.id, version_id: publicada.id } },
          }),
        );
        for (const i of itens) {
          if (!mapa.has(i.procedure_code)) {
            mapa.set(i.procedure_code, { codigo: i.procedure_code, descricao: i.description, categoria: i.category });
          }
        }
      }
      return [...mapa.values()].sort((a, b) => a.descricao.localeCompare(b.descricao));
    },
  });
}
