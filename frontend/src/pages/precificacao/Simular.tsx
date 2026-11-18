import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { api, mensagemErro, type Schemas } from "../../api/client";
import { Aviso, Botao, Campo, Cartao, Selecao } from "../../components/ui";
import { dinheiro } from "../../lib/datas";
import { useDentistas } from "../../lib/equipe";
import { useProcedimentos } from "../../lib/procedimentos";

/** "Quanto sai este procedimento para este dentista?" com a memória de cálculo. */
export default function Simular() {
  const dentistas = useDentistas();
  const procedimentos = useProcedimentos();
  const [codigo, setCodigo] = useState("");
  const [dentista, setDentista] = useState("");
  const simular = useMutation({
    mutationFn: async () => {
      const r = await api.POST("/precificacao/resolver", {
        body: { procedure_code: codigo.trim(), dentist_id: dentista || null },
      });
      if (!r.data) throw new Error(mensagemErro(r.error, "Sem preço para este procedimento."));
      return r.data as Schemas["ResolutionOut"];
    },
  });
  const r = simular.data;
  return (
    <Cartao titulo="Simular preço">
      <div className="flex flex-wrap items-end gap-3">
        <Campo rotulo="Procedimento" list="sim-procedimentos" value={codigo} onChange={(e) => setCodigo(e.target.value)} />
        <datalist id="sim-procedimentos">
          {procedimentos.data?.map((p) => (
            <option key={p.codigo} value={p.codigo}>
              {p.descricao}
            </option>
          ))}
        </datalist>
        <Selecao rotulo="Dentista" value={dentista} onChange={(e) => setDentista(e.target.value)}>
          <option value="">— clínica —</option>
          {dentistas.data?.map((d) => (
            <option key={d.user_id} value={d.user_id}>
              {d.full_name}
            </option>
          ))}
        </Selecao>
        <Botao onClick={() => simular.mutate()} disabled={!codigo.trim()} carregando={simular.isPending}>
          Simular
        </Botao>
      </div>
      {simular.error && (
        <div className="mt-3">
          <Aviso tom="perigo">{simular.error.message}</Aviso>
        </div>
      )}
      {r && (
        <div className="mt-4 flex flex-col gap-2">
          <p className="text-2xl font-bold">{dinheiro(r.price)}</p>
          <p className="text-sm">{r.description}</p>
          <details className="rounded-lg border border-borda p-3 text-sm">
            <summary className="min-h-8 cursor-pointer font-semibold">Memória de cálculo</summary>
            <ol className="mt-2 list-decimal pl-5 text-xs">
              {r.trace.map((passo, i) => (
                <li key={i} className="font-mono break-all">
                  {Object.entries(passo)
                    .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
                    .join(" · ")}
                </li>
              ))}
            </ol>
          </details>
        </div>
      )}
    </Cartao>
  );
}
