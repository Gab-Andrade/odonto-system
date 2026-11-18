import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok } from "../../api/client";
import { Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Selecao } from "../../components/ui";
import { nomeMembro, useDentistas } from "../../lib/equipe";

/** A quem cada tabela se aplica. Na resolução do preço, a menor prioridade vence. */
export default function Atribuicoes() {
  const cliente = useQueryClient();
  const dentistas = useDentistas();
  const [tabela, setTabela] = useState("");
  const [escopo, setEscopo] = useState<"clinica" | "dentista">("clinica");
  const [dentista, setDentista] = useState("");
  const [prioridade, setPrioridade] = useState("");
  const tabelas = useQuery({
    queryKey: ["precificacao", "tabelas"],
    queryFn: async () => ok(await api.GET("/precificacao/tabelas")),
  });
  const lista = useQuery({
    queryKey: ["precificacao", "atribuicoes"],
    queryFn: async () => ok(await api.GET("/precificacao/atribuicoes")),
  });
  const pronto = () => cliente.invalidateQueries({ queryKey: ["precificacao", "atribuicoes"] });
  const criar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/precificacao/atribuicoes", {
          body: {
            table_id: tabela,
            scope_type: escopo,
            scope_id: escopo === "dentista" ? dentista : null,
            priority: prioridade ? Number(prioridade) : null,
          },
        }),
      ),
    onSuccess: pronto,
  });
  const remover = useMutation({
    mutationFn: async (id: string) =>
      ok(await api.DELETE("/precificacao/atribuicoes/{assignment_id}", { params: { path: { assignment_id: id } } })),
    onSuccess: pronto,
  });
  const nomeTabela = (id: string) => tabelas.data?.find((t) => t.id === id)?.name ?? "—";

  return (
    <div className="flex flex-col gap-4">
      <Cartao titulo="Atribuir tabela">
        {criar.error && <Aviso tom="perigo">{criar.error.message}</Aviso>}
        <div className="flex flex-wrap items-end gap-3">
          <Selecao rotulo="Tabela" value={tabela} onChange={(e) => setTabela(e.target.value)}>
            <option value="">Escolha</option>
            {tabelas.data
              ?.filter((t) => t.status === "ativa")
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
          </Selecao>
          <Selecao rotulo="Para" value={escopo} onChange={(e) => setEscopo(e.target.value as "clinica" | "dentista")}>
            <option value="clinica">A clínica toda</option>
            <option value="dentista">Um dentista</option>
          </Selecao>
          {escopo === "dentista" && (
            <Selecao rotulo="Dentista" value={dentista} onChange={(e) => setDentista(e.target.value)}>
              <option value="">Escolha</option>
              {dentistas.data?.map((d) => (
                <option key={d.user_id} value={d.user_id}>
                  {d.full_name}
                </option>
              ))}
            </Selecao>
          )}
          <Campo rotulo="Prioridade" type="number" className="w-32" placeholder="padrão" value={prioridade} onChange={(e) => setPrioridade(e.target.value)} />
          <Botao onClick={() => criar.mutate()} disabled={!tabela || (escopo === "dentista" && !dentista)} carregando={criar.isPending}>
            Atribuir
          </Botao>
        </div>
        <p className="mt-2 text-xs text-texto-suave">
          Ordem padrão: convênio (10) → dentista (20) → clínica (30). Se o procedimento não está numa tabela, o preço vem da próxima.
        </p>
      </Cartao>
      <Cartao titulo="Atribuições">
        {lista.isLoading && <Carregando />}
        {lista.error && <ErroCarga erro={lista.error} />}
        <ul className="divide-y divide-borda">
          {lista.data?.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
              <span className="w-12 font-mono">{a.priority}</span>
              <span className="flex-1">
                {nomeTabela(a.table_id)} → {a.scope_type === "clinica" ? "clínica" : `${a.scope_type}: ${nomeMembro(dentistas.data, a.scope_id)}`}
              </span>
              <Botao variante="fantasma" onClick={() => remover.mutate(a.id)}>
                Remover
              </Botao>
            </li>
          ))}
          {lista.data?.length === 0 && <li className="py-2 text-sm text-texto-suave">Nenhuma atribuição: os orçamentos não vão achar preço.</li>}
        </ul>
      </Cartao>
    </div>
  );
}
