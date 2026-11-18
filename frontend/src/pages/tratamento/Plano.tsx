import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import { temPapel, useSessao } from "../../auth/sessao";
import Modal from "../../components/Modal";
import { Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Selecao } from "../../components/ui";
import { dataBR, dataHoraBR, dinheiro } from "../../lib/datas";
import { nomeMembro, useEquipe } from "../../lib/equipe";
import { useProcedimentos } from "../../lib/procedimentos";
import { NOME_ITEM, NOME_PLANO, TOM_ITEM, TOM_PLANO } from "./status";

type PlanoOut = Schemas["PlanOut"];
type Item = Schemas["app__modules__tratamento__schemas__ItemOut"];

export default function Plano({
  planoId,
  paciente,
  aoVoltar,
}: {
  planoId: string;
  paciente: Schemas["PatientOut"];
  aoVoltar: () => void;
}) {
  const { papel, usuario } = useSessao();
  const cliente = useQueryClient();
  const equipe = useEquipe();
  const [erro, setErro] = useState<string | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [novoItem, setNovoItem] = useState(false);
  const [decidir, setDecidir] = useState(false);
  const [parcelar, setParcelar] = useState(false);
  const chave = ["plano", planoId];

  const plano = useQuery({
    queryKey: chave,
    queryFn: async () =>
      ok(await api.GET("/tratamento/planos/{plan_id}", { params: { path: { plan_id: planoId } } })),
  });
  const atendimentos = useQuery({
    queryKey: ["atendimentos", paciente.id],
    queryFn: async () =>
      ok(
        await api.GET("/prontuario/pacientes/{patient_id}/atendimentos", {
          params: { path: { patient_id: paciente.id } },
        }),
      ),
  });

  const aplicar = (p: PlanoOut) => {
    cliente.setQueryData(chave, p);
    cliente.invalidateQueries({ queryKey: ["planos", paciente.id] });
    cliente.invalidateQueries({ queryKey: ["odontograma", paciente.id] });
    setAvisos(p.warnings ?? []);
    setErro(null);
  };
  const acao = useMutation({
    mutationFn: async (f: () => Promise<PlanoOut>) => f(),
    onSuccess: aplicar,
    onError: (e) => setErro(e.message),
  });

  if (plano.isLoading) return <Carregando />;
  if (plano.error) return <ErroCarga erro={plano.error} />;
  const p = plano.data!;
  const rascunho = p.status === "rascunho";
  const monta = temPapel(papel, "admin", "dentista");
  const vende = temPapel(papel, "admin", "gestor", "dentista", "recepcao");
  const meuAberto = (atendimentos.data ?? []).find((a) => a.status === "aberto" && a.dentist_id === usuario?.id);
  const path = { plan_id: p.id };

  const emitir = () =>
    acao.mutate(async () => ok(await api.POST("/tratamento/planos/{plan_id}/emitir", { params: { path } })));
  const duplicar = () =>
    acao.mutate(async () => ok(await api.POST("/tratamento/planos/{plan_id}/duplicar", { params: { path } })));
  const cancelarPlano = () => {
    const motivo = window.prompt("Motivo do cancelamento:");
    if (motivo?.trim())
      acao.mutate(async () =>
        ok(await api.POST("/tratamento/planos/{plan_id}/cancelar", { params: { path }, body: { reason: motivo.trim() } })),
      );
  };
  const desconto = () => {
    const v = window.prompt("Desconto (%) sobre o total:", String(p.discount_pct));
    if (v !== null)
      acao.mutate(async () =>
        ok(
          await api.POST("/tratamento/planos/{plan_id}/desconto", {
            params: { path },
            body: { discount_pct: v.replace(",", ".") },
          }),
        ),
      );
  };
  const removerItem = (i: Item) =>
    acao.mutate(async () => {
      ok(await api.DELETE("/tratamento/itens/{item_id}", { params: { path: { item_id: i.id } } }));
      return ok(await api.GET("/tratamento/planos/{plan_id}", { params: { path } }));
    });
  const realizar = (i: Item) =>
    acao.mutate(async () =>
      ok(
        await api.POST("/tratamento/itens/{item_id}/realizar", {
          params: { path: { item_id: i.id } },
          body: { encounter_id: meuAberto!.id },
        }),
      ),
    );
  const cancelarItem = (i: Item) => {
    const motivo = window.prompt("Motivo do cancelamento do item:");
    if (motivo?.trim())
      acao.mutate(async () =>
        ok(
          await api.POST("/tratamento/itens/{item_id}/cancelar", {
            params: { path: { item_id: i.id } },
            body: { reason: motivo.trim() },
          }),
        ),
      );
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="nao-imprimir flex flex-wrap items-center gap-2">
        <Botao variante="fantasma" onClick={aoVoltar}>
          ← Planos
        </Botao>
        <span className="flex-1" />
        {rascunho && monta && (
          <Botao variante="secundario" onClick={() => setNovoItem(true)}>
            + Procedimento
          </Botao>
        )}
        {rascunho && vende && (
          <Botao variante="secundario" onClick={desconto}>
            Desconto
          </Botao>
        )}
        {rascunho && vende && (
          <Botao onClick={emitir} carregando={acao.isPending} disabled={p.items.length === 0}>
            Emitir orçamento
          </Botao>
        )}
        {p.status === "emitido" && vende && !p.expired && <Botao onClick={() => setDecidir(true)}>Registrar decisão</Botao>}
        {["aprovado", "concluido"].includes(p.status) && temPapel(papel, "admin", "gestor", "recepcao") && (
          <Botao variante="secundario" onClick={() => setParcelar(true)}>
            Parcelar
          </Botao>
        )}
        {(p.expired || ["recusado", "cancelado"].includes(p.status)) && monta && (
          <Botao variante="secundario" onClick={duplicar}>
            Duplicar
          </Botao>
        )}
        {["rascunho", "emitido"].includes(p.status) && vende && (
          <Botao variante="perigo" onClick={cancelarPlano}>
            Cancelar
          </Botao>
        )}
        {p.status !== "rascunho" && (
          <Botao variante="secundario" onClick={() => window.print()}>
            Imprimir
          </Botao>
        )}
      </div>

      {erro && <Aviso tom="perigo">{erro}</Aviso>}
      {avisos.length > 0 && <Aviso tom="alerta">{avisos.join(" ")}</Aviso>}

      <Cartao
        titulo={
          <span className="flex flex-wrap items-center gap-2">
            {p.title ?? "Plano"} · {paciente.full_name}
            <Etiqueta tom={TOM_PLANO[p.status]}>{NOME_PLANO[p.status]}</Etiqueta>
            {p.expired && <Etiqueta tom="perigo">Vencido</Etiqueta>}
          </span>
        }
      >
        <p className="mb-3 text-sm text-texto-suave">
          Responsável: {nomeMembro(equipe.data, p.dentist_id)}
          {p.issued_at && ` · emitido em ${dataHoraBR(p.issued_at)}`}
          {p.valid_until && ` · válido até ${dataBR(p.valid_until)}`}
        </p>
        {rascunho && p.items.length > 0 && (
          <p className="mb-2 text-xs text-texto-suave">
            No rascunho o preço é uma estimativa; ele é congelado na emissão.
          </p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-borda text-left text-xs text-texto-suave">
                <th className="py-2">Procedimento</th>
                <th>Dente/faces</th>
                <th className="text-right">Valor</th>
                <th>Situação</th>
                <th className="nao-imprimir" />
              </tr>
            </thead>
            <tbody>
              {p.items.map((i) => (
                <tr key={i.id} className="border-b border-borda/60">
                  <td className="py-2">
                    <p className="font-medium">{i.description ?? i.procedure_code}</p>
                    <p className="text-xs text-texto-suave">{i.procedure_code}</p>
                    {i.estimate_error && <p className="text-xs text-perigo">{i.estimate_error}</p>}
                  </td>
                  <td>{i.tooth ? `${i.tooth}${i.faces ? ` ${i.faces}` : ""}` : "—"}</td>
                  <td className="text-right">{dinheiro(i.unit_price ?? i.estimated_price)}</td>
                  <td>
                    <Etiqueta tom={TOM_ITEM[i.status]}>{NOME_ITEM[i.status]}</Etiqueta>
                    {i.performed_at && <p className="text-xs text-texto-suave">{dataBR(i.performed_at)}</p>}
                  </td>
                  <td className="nao-imprimir text-right whitespace-nowrap">
                    {rascunho && monta && (
                      <Botao variante="fantasma" onClick={() => removerItem(i)}>
                        Remover
                      </Botao>
                    )}
                    {i.status === "aprovado" && monta && (
                      <Botao
                        variante="secundario"
                        disabled={!meuAberto}
                        title={meuAberto ? "" : "Abra um atendimento seu para registrar"}
                        onClick={() => realizar(i)}
                      >
                        Realizado
                      </Botao>
                    )}
                    {i.status === "aprovado" && temPapel(papel, "admin", "gestor", "dentista") && (
                      <Botao variante="fantasma" onClick={() => cancelarItem(i)}>
                        Cancelar
                      </Botao>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <dl className="mt-3 grid justify-end gap-1 text-sm">
          <div className="flex justify-between gap-6">
            <dt>Total proposto</dt>
            <dd>{dinheiro(p.totals.proposed)}</dd>
          </div>
          {Number(p.discount_pct) > 0 && (
            <div className="flex justify-between gap-6">
              <dt>Desconto ({p.discount_pct}%)</dt>
              <dd>− {dinheiro(p.totals.discount)}</dd>
            </div>
          )}
          {p.decided_at && (
            <div className="flex justify-between gap-6 font-bold">
              <dt>Total aprovado</dt>
              <dd>{dinheiro(p.totals.approved_total)}</dd>
            </div>
          )}
        </dl>
        {p.items.some((i) => i.status === "aprovado") && monta && !meuAberto && (
          <p className="nao-imprimir mt-2 text-xs text-texto-suave">
            Para marcar procedimento como realizado, abra um atendimento seu (aba Atendimentos).
          </p>
        )}
        <div className="hidden print:block print:pt-12">
          <p>______________________________________</p>
          <p className="text-sm">Assinatura do paciente ou responsável</p>
        </div>
      </Cartao>

      {novoItem && <NovoItem plano={p} aoFechar={() => setNovoItem(false)} aoSalvar={aplicar} />}
      {decidir && <Decisao plano={p} aoFechar={() => setDecidir(false)} aoSalvar={aplicar} />}
      {parcelar && <Parcelar plano={p} pacienteId={paciente.id} aoFechar={() => setParcelar(false)} />}
    </div>
  );
}

function NovoItem({ plano, aoFechar, aoSalvar }: { plano: PlanoOut; aoFechar: () => void; aoSalvar: (p: PlanoOut) => void }) {
  const procedimentos = useProcedimentos();
  const legenda = useQuery({
    queryKey: ["odontograma", "legenda"],
    queryFn: async () => ok(await api.GET("/odontograma/legenda")),
  });
  const [codigo, setCodigo] = useState("");
  const [dente, setDente] = useState("");
  const [faces, setFaces] = useState("");
  const [planejado, setPlanejado] = useState("");
  const [feito, setFeito] = useState("");
  const salvar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/tratamento/planos/{plan_id}/itens", {
          params: { path: { plan_id: plano.id } },
          body: {
            procedure_code: codigo.trim(),
            tooth: dente ? Number(dente) : null,
            faces: faces || null,
            planned_status_id: planejado || null,
            done_status_id: feito || null,
          },
        }),
      ),
    onSuccess: (p) => {
      aoSalvar(p);
      aoFechar();
    },
  });
  const ativos = (legenda.data ?? []).filter((l) => l.active);

  return (
    <Modal titulo="Adicionar procedimento" aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        <Campo rotulo="Procedimento (código)" list="lista-procedimentos" value={codigo} onChange={(e) => setCodigo(e.target.value)} dica="Escolha da lista ou digite o código da tabela de preços." />
        <datalist id="lista-procedimentos">
          {procedimentos.data?.map((pr) => (
            <option key={pr.codigo} value={pr.codigo}>
              {pr.descricao}
            </option>
          ))}
        </datalist>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo="Dente (FDI)" inputMode="numeric" value={dente} onChange={(e) => setDente(e.target.value)} />
          <Campo rotulo="Faces" placeholder="MOD" value={faces} onChange={(e) => setFaces(e.target.value.toUpperCase())} />
          <Selecao rotulo="No odontograma, 'a fazer'" value={planejado} onChange={(e) => setPlanejado(e.target.value)}>
            <option value="">—</option>
            {ativos.filter((l) => l.kind === "planejado").map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </Selecao>
          <Selecao rotulo="Ao realizar, marcar" value={feito} onChange={(e) => setFeito(e.target.value)}>
            <option value="">—</option>
            {ativos.filter((l) => l.kind === "realizado").map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </Selecao>
        </div>
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao onClick={() => salvar.mutate()} carregando={salvar.isPending} disabled={!codigo.trim()}>
            Adicionar
          </Botao>
        </div>
      </div>
    </Modal>
  );
}

function Decisao({ plano, aoFechar, aoSalvar }: { plano: PlanoOut; aoFechar: () => void; aoSalvar: (p: PlanoOut) => void }) {
  const [aprovados, setAprovados] = useState<string[]>(plano.items.map((i) => i.id));
  const salvar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/tratamento/planos/{plan_id}/decisao", {
          params: { path: { plan_id: plano.id } },
          body: { approved_item_ids: aprovados },
        }),
      ),
    onSuccess: (p) => {
      aoSalvar(p);
      aoFechar();
    },
  });
  return (
    <Modal titulo="Decisão do paciente" aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        <p className="text-sm text-texto-suave">Marque o que o paciente aprovou; o resto fica recusado.</p>
        {plano.items.map((i) => (
          <label key={i.id} className="flex min-h-11 items-center gap-3 text-sm">
            <input
              type="checkbox"
              className="size-5"
              checked={aprovados.includes(i.id)}
              onChange={(e) => setAprovados(e.target.checked ? [...aprovados, i.id] : aprovados.filter((x) => x !== i.id))}
            />
            <span className="flex-1">
              {i.description ?? i.procedure_code} {i.tooth && `(${i.tooth}${i.faces ? ` ${i.faces}` : ""})`}
            </span>
            <span>{dinheiro(i.unit_price)}</span>
          </label>
        ))}
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao onClick={() => salvar.mutate()} carregando={salvar.isPending}>
            {aprovados.length === 0 ? "Registrar recusa" : `Aprovar ${aprovados.length} item(ns)`}
          </Botao>
        </div>
      </div>
    </Modal>
  );
}

function Parcelar({ plano, pacienteId, aoFechar }: { plano: PlanoOut; pacienteId: string; aoFechar: () => void }) {
  const cliente = useQueryClient();
  const [entrada, setEntrada] = useState("0");
  const [parcelas, setParcelas] = useState("3");
  const salvar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/financeiro/planos/{plan_id}/parcelamento", {
          params: { path: { plan_id: plano.id } },
          body: { down_payment: entrada.replace(",", ".") || "0", installments: Number(parcelas) || 0 },
        }),
      ),
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["financeiro", pacienteId] });
      aoFechar();
    },
  });
  return (
    <Modal titulo="Parcelar orçamento aprovado" aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        {salvar.isSuccess && <Aviso tom="sucesso">Parcelas geradas. Veja na aba Financeiro.</Aviso>}
        <p className="text-sm">Total aprovado: {dinheiro(plano.totals.approved_total)}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo="Entrada (R$)" inputMode="decimal" value={entrada} onChange={(e) => setEntrada(e.target.value)} />
          <Campo rotulo="Parcelas mensais" type="number" min={0} max={36} value={parcelas} onChange={(e) => setParcelas(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Fechar
          </Botao>
          <Botao onClick={() => salvar.mutate()} carregando={salvar.isPending}>
            Gerar parcelas
          </Botao>
        </div>
      </div>
    </Modal>
  );
}
