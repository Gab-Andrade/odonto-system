import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import { temPapel, useSessao } from "../../auth/sessao";
import { Botao, Cartao, Carregando, ErroCarga, Etiqueta, Vazio } from "../../components/ui";
import { dataBR } from "../../lib/datas";
import { nomeMembro, useEquipe } from "../../lib/equipe";
import Plano from "./Plano";
import { NOME_PLANO, TOM_PLANO } from "./status";

type Paciente = Schemas["PatientOut"];

export default function Planos({ paciente }: { paciente: Paciente }) {
  const { papel } = useSessao();
  const cliente = useQueryClient();
  const equipe = useEquipe();
  const [aberto, setAberto] = useState<string | null>(null);
  const podeMontar = temPapel(papel, "admin", "dentista");

  const planos = useQuery({
    queryKey: ["planos", paciente.id],
    queryFn: async () =>
      ok(
        await api.GET("/tratamento/pacientes/{patient_id}/planos", {
          params: { path: { patient_id: paciente.id } },
        }),
      ),
  });

  const criar = useMutation({
    mutationFn: async () =>
      ok(await api.POST("/tratamento/planos", { body: { patient_id: paciente.id, title: "Plano de tratamento" } })),
    onSuccess: (p) => {
      cliente.invalidateQueries({ queryKey: ["planos", paciente.id] });
      setAberto(p.id);
    },
  });

  if (aberto) {
    return <Plano planoId={aberto} paciente={paciente} aoVoltar={() => setAberto(null)} />;
  }

  return (
    <div className="flex flex-col gap-4">
      {podeMontar && (
        <Botao className="self-start" onClick={() => criar.mutate()} carregando={criar.isPending}>
          + Novo plano
        </Botao>
      )}
      {criar.error && <ErroCarga erro={criar.error} />}
      {planos.isLoading && <Carregando />}
      {planos.error && <ErroCarga erro={planos.error} />}
      {planos.data && planos.data.length === 0 && (
        <Cartao>
          <Vazio>Nenhum plano de tratamento.</Vazio>
        </Cartao>
      )}
      <ul className="flex flex-col gap-2">
        {planos.data?.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => setAberto(p.id)}
              className="flex min-h-14 w-full flex-wrap items-center gap-3 rounded-xl border border-borda bg-painel p-3 text-left hover:border-marca"
            >
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{p.title ?? "Plano"}</p>
                <p className="text-xs text-texto-suave">
                  {nomeMembro(equipe.data, p.dentist_id)} · criado em {dataBR(p.created_at)}
                  {p.valid_until && ` · válido até ${dataBR(p.valid_until)}`}
                  {Number(p.discount_pct) > 0 && ` · desconto ${p.discount_pct}%`}
                </p>
              </div>
              {p.expired && <Etiqueta tom="perigo">Vencido</Etiqueta>}
              <Etiqueta tom={TOM_PLANO[p.status]}>{NOME_PLANO[p.status]}</Etiqueta>
            </button>
          </li>
        ))}
      </ul>
      <p className="text-xs text-texto-suave">O preço é congelado na emissão do orçamento.</p>
    </div>
  );
}
