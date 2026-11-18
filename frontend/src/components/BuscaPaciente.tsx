import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";

import { api, ok } from "../api/client";
import { Campo, Spinner } from "./ui";

export interface PacienteEscolhido {
  id: string;
  nome: string;
}

/** Campo de busca de paciente com lista de resultados (toque para escolher). */
export default function BuscaPaciente({
  valor,
  aoEscolher,
}: {
  valor: PacienteEscolhido | null;
  aoEscolher: (p: PacienteEscolhido | null) => void;
}) {
  const [termo, setTermo] = useState("");
  const busca = useDeferredValue(termo.trim());
  const resultados = useQuery({
    enabled: busca.length >= 2 && !valor,
    queryKey: ["pacientes", "busca", busca, false],
    queryFn: async () =>
      ok(await api.GET("/pacientes", { params: { query: { busca, limit: 8 } } })),
  });

  if (valor) {
    return (
      <div className="flex flex-col gap-1 text-sm">
        <span className="font-medium text-texto-suave">Paciente</span>
        <div className="flex min-h-11 items-center justify-between rounded-lg border border-marca bg-marca-suave px-3">
          <span className="font-medium">{valor.nome}</span>
          <button type="button" className="min-h-11 px-2 text-marca" onClick={() => aoEscolher(null)}>
            trocar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="relative">
      <Campo
        rotulo="Paciente"
        placeholder="Digite nome, CPF ou telefone"
        value={termo}
        onChange={(e) => setTermo(e.target.value)}
        autoFocus
      />
      {resultados.isFetching && (
        <span className="absolute top-9 right-3">
          <Spinner />
        </span>
      )}
      {resultados.data && busca.length >= 2 && (
        <ul className="absolute inset-x-0 z-10 mt-1 max-h-64 overflow-y-auto rounded-lg border border-borda bg-painel shadow-lg">
          {resultados.data.length === 0 && (
            <li className="p-3 text-sm text-texto-suave">Nenhum paciente encontrado.</li>
          )}
          {resultados.data.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                className="flex min-h-11 w-full flex-col items-start px-3 py-2 text-left hover:bg-fundo"
                onClick={() => aoEscolher({ id: p.id, nome: p.social_name ?? p.full_name })}
              >
                <span className="font-medium">{p.social_name ?? p.full_name}</span>
                <span className="text-xs text-texto-suave">{p.phone}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
