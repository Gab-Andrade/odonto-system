import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import { GESTAO, temPapel, useSessao } from "../../auth/sessao";
import Modal from "../../components/Modal";
import { Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Selecao, Vazio } from "../../components/ui";
import { dataBR, dataHoraBR, dinheiro, hojeISO } from "../../lib/datas";
import { nomeMembro, useDentistas, useEquipe } from "../../lib/equipe";
import { useProcedimentos } from "../../lib/procedimentos";

/**
 * Repasse: regras de comissão por dentista, prévia do quanto ele recebe até uma data
 * (sobre o que o paciente já pagou) e fechamentos. Gestão vê todos e fecha; o dentista
 * vê só o próprio.
 */

type Linha = Schemas["LineOut"];

export default function Repasse() {
  const sessao = useSessao();
  const gestao = temPapel(sessao.papel, ...GESTAO);
  const dentistas = useDentistas();
  const [escolhido, setEscolhido] = useState("");
  const dentista = gestao ? escolhido : (sessao.usuario?.id ?? "");

  return (
    <div className="flex flex-col gap-4">
      {gestao && (
        <Selecao rotulo="Dentista" value={escolhido} onChange={(e) => setEscolhido(e.target.value)} className="max-w-sm">
          <option value="">— escolha —</option>
          {dentistas.data?.map((d) => (
            <option key={d.user_id} value={d.user_id}>
              {d.full_name}
            </option>
          ))}
        </Selecao>
      )}
      {dentista ? (
        <>
          <Previa dentista={dentista} gestao={gestao} />
          <Regras dentista={dentista} gestao={gestao} />
          <Fechamentos dentista={dentista} />
        </>
      ) : (
        <Cartao>
          <Vazio>Escolha o dentista para ver as regras, a prévia e os fechamentos.</Vazio>
        </Cartao>
      )}
    </div>
  );
}

function TabelaLinhas({ linhas }: { linhas: Linha[] }) {
  const procs = useProcedimentos();
  const nome = (c: string) => procs.data?.find((p) => p.codigo === c)?.descricao ?? c;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <thead className="text-left text-xs text-texto-suave">
          <tr>
            <th className="py-1 pr-3 font-medium">Procedimento</th>
            <th className="py-1 pr-3 text-right font-medium">Base recebida</th>
            <th className="py-1 pr-3 text-right font-medium">− Taxa</th>
            <th className="py-1 pr-3 text-right font-medium">− Material</th>
            <th className="py-1 text-right font-medium">Repasse</th>
          </tr>
        </thead>
        <tbody>
          {linhas.map((l) => (
            <tr key={`${l.plan_item_id}-${l.rule_id}`} className="border-t border-borda">
              <td className="py-2 pr-3">{nome(l.procedure_code)}</td>
              <td className="py-2 pr-3 text-right">{dinheiro(l.base_amount)}</td>
              <td className="py-2 pr-3 text-right">{Number(l.fee_deduction) ? dinheiro(l.fee_deduction) : "—"}</td>
              <td className="py-2 pr-3 text-right">{Number(l.material_deduction) ? dinheiro(l.material_deduction) : "—"}</td>
              <td className={`py-2 text-right font-semibold ${Number(l.commission) < 0 ? "text-perigo" : ""}`}>{dinheiro(l.commission)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Previa({ dentista, gestao }: { dentista: string; gestao: boolean }) {
  const cliente = useQueryClient();
  const [ate, setAte] = useState(hojeISO());
  const [obs, setObs] = useState("");
  const [confirmar, setConfirmar] = useState(false);
  const previa = useQuery({
    enabled: !!ate,
    queryKey: ["repasse", "previa", dentista, ate],
    queryFn: async () => ok(await api.GET("/repasse/previa", { params: { query: { ate, dentista_id: dentista } } })),
  });
  const fechar = useMutation({
    mutationFn: async () =>
      ok(await api.POST("/repasse/fechamentos", { body: { dentist_id: dentista, period_end: ate, notes: obs.trim() || null } })),
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["repasse"] });
      setConfirmar(false);
      setObs("");
    },
  });
  const p = previa.data;
  return (
    <Cartao titulo="Prévia do repasse">
      <div className="flex flex-wrap items-end gap-3">
        <Campo rotulo="Até" type="date" max={hojeISO()} value={ate} onChange={(e) => setAte(e.target.value)} />
        {p && (
          <p className="pb-2 text-sm">
            {p.period_start ? `Desde ${dataBR(p.period_start)} (último fechamento)` : "Desde o início"} ·{" "}
            <strong className="text-lg">{dinheiro(p.total)}</strong>
          </p>
        )}
        {gestao && p && p.lines.length > 0 && (
          <Botao className="ml-auto" onClick={() => setConfirmar(true)}>
            Fechar repasse até {dataBR(ate)}
          </Botao>
        )}
      </div>
      {previa.isLoading && <Carregando />}
      {previa.error && <div className="mt-3"><ErroCarga erro={previa.error} /></div>}
      {fechar.isSuccess && <div className="mt-3"><Aviso tom="sucesso">Repasse fechado.</Aviso></div>}
      {p && p.missing_rule.length > 0 && (
        <div className="mt-3">
          <Aviso tom="alerta">
            Procedimentos realizados sem regra de repasse (não entram até ter regra): {p.missing_rule.join(", ")}.
          </Aviso>
        </div>
      )}
      {p && p.lines.length === 0 && <Vazio>Nada a repassar neste período: só entra o que o paciente já pagou.</Vazio>}
      {p && p.lines.length > 0 && (
        <div className="mt-3">
          <TabelaLinhas linhas={p.lines} />
        </div>
      )}
      {confirmar && p && (
        <Modal titulo="Fechar repasse" aberto aoFechar={() => setConfirmar(false)}>
          <div className="flex flex-col gap-3">
            <p className="text-sm">
              Fecha <strong>{dinheiro(p.total)}</strong> até {dataBR(ate)}. O fechamento não pode ser desfeito; pagamentos e
              estornos depois desta data entram no próximo.
            </p>
            {fechar.error && <Aviso tom="perigo">{fechar.error.message}</Aviso>}
            <Campo rotulo="Observação (opcional)" value={obs} onChange={(e) => setObs(e.target.value)} />
            <div className="flex justify-end gap-2">
              <Botao variante="secundario" onClick={() => setConfirmar(false)}>
                Voltar
              </Botao>
              <Botao onClick={() => fechar.mutate()} carregando={fechar.isPending}>
                Fechar repasse
              </Botao>
            </div>
          </div>
        </Modal>
      )}
    </Cartao>
  );
}

function Regras({ dentista, gestao }: { dentista: string; gestao: boolean }) {
  const [nova, setNova] = useState(false);
  const procs = useProcedimentos();
  const regras = useQuery({
    queryKey: ["repasse", "regras", dentista],
    queryFn: async () => ok(await api.GET("/repasse/regras", { params: { query: { dentista_id: dentista } } })),
  });
  const lista = [...(regras.data ?? [])].sort((a, b) => b.valid_from.localeCompare(a.valid_from));
  return (
    <Cartao titulo="Regras de repasse" acoes={gestao && <Botao variante="secundario" onClick={() => setNova(true)}>+ Nova regra</Botao>}>
      {regras.isLoading && <Carregando />}
      {regras.error && <ErroCarga erro={regras.error} />}
      {regras.data && lista.length === 0 && <Vazio>Sem regra: nada é repassado até cadastrar uma.</Vazio>}
      <ul className="flex flex-col divide-y divide-borda">
        {lista.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
            <span className="font-semibold">{r.kind === "percentual" ? `${Number(r.value)}%` : `${dinheiro(r.value)} por procedimento`}</span>
            <span className="text-texto-suave">
              {r.procedure_code ? (procs.data?.find((p) => p.codigo === r.procedure_code)?.descricao ?? r.procedure_code) : "regra geral"} · vale
              desde {dataBR(r.valid_from)}
            </span>
            {r.deduct_card_fee && <Etiqueta>desconta taxa</Etiqueta>}
            {r.deduct_materials && <Etiqueta>desconta material</Etiqueta>}
          </li>
        ))}
      </ul>
      {regras.data && lista.length > 0 && (
        <p className="mt-2 text-xs text-texto-suave">
          A regra do procedimento vale sobre a geral. Para mudar, cadastre outra com nova data: a antiga continua valendo para o que foi feito antes.
        </p>
      )}
      {nova && <NovaRegra dentista={dentista} aoFechar={() => setNova(false)} />}
    </Cartao>
  );
}

function NovaRegra({ dentista, aoFechar }: { dentista: string; aoFechar: () => void }) {
  const cliente = useQueryClient();
  const procs = useProcedimentos();
  const [procedimento, setProcedimento] = useState("");
  const [tipo, setTipo] = useState<"percentual" | "fixo">("percentual");
  const [valor, setValor] = useState("");
  const [taxa, setTaxa] = useState(false);
  const [material, setMaterial] = useState(false);
  const [desde, setDesde] = useState(hojeISO());
  const salvar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/repasse/regras", {
          body: {
            dentist_id: dentista,
            procedure_code: procedimento || null,
            kind: tipo,
            value: valor.trim().replace(",", "."),
            deduct_card_fee: tipo === "percentual" && taxa,
            deduct_materials: tipo === "percentual" && material,
            valid_from: desde || null,
          },
        }),
      ),
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["repasse"] });
      aoFechar();
    },
  });
  return (
    <Modal titulo="Nova regra de repasse" aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        <Selecao rotulo="Vale para" value={procedimento} onChange={(e) => setProcedimento(e.target.value)}>
          <option value="">Todos os procedimentos (regra geral)</option>
          {procs.data?.map((p) => (
            <option key={p.codigo} value={p.codigo}>
              {p.descricao}
            </option>
          ))}
        </Selecao>
        <div className="grid gap-3 sm:grid-cols-3">
          <Selecao rotulo="Tipo" value={tipo} onChange={(e) => setTipo(e.target.value as "percentual" | "fixo")}>
            <option value="percentual">Percentual</option>
            <option value="fixo">Valor fixo</option>
          </Selecao>
          <Campo rotulo={tipo === "percentual" ? "Percentual (%)" : "Valor (R$)"} inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} />
          <Campo rotulo="Vale desde" type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
        </div>
        {tipo === "percentual" ? (
          <div className="flex flex-col gap-1 text-sm">
            <label className="flex min-h-10 items-center gap-2">
              <input type="checkbox" className="size-5 accent-marca" checked={taxa} onChange={(e) => setTaxa(e.target.checked)} />
              Descontar a taxa do cartão antes do percentual
            </label>
            <label className="flex min-h-10 items-center gap-2">
              <input type="checkbox" className="size-5 accent-marca" checked={material} onChange={(e) => setMaterial(e.target.checked)} />
              Descontar o material usado (custo do estoque)
            </label>
          </div>
        ) : (
          <p className="text-xs text-texto-suave">O valor fixo é pago na proporção do que o paciente já pagou.</p>
        )}
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao onClick={() => salvar.mutate()} carregando={salvar.isPending} disabled={!valor.trim()}>
            Salvar regra
          </Botao>
        </div>
      </div>
    </Modal>
  );
}

function Fechamentos({ dentista }: { dentista: string }) {
  const equipe = useEquipe();
  const [aberto, setAberto] = useState<string | null>(null);
  const fechamentos = useQuery({
    queryKey: ["repasse", "fechamentos", dentista],
    queryFn: async () => ok(await api.GET("/repasse/fechamentos", { params: { query: { dentista_id: dentista } } })),
  });
  const lista = [...(fechamentos.data ?? [])].sort((a, b) => b.period_end.localeCompare(a.period_end));
  return (
    <Cartao titulo="Fechamentos">
      {fechamentos.isLoading && <Carregando />}
      {fechamentos.error && <ErroCarga erro={fechamentos.error} />}
      {fechamentos.data && lista.length === 0 && <Vazio>Nenhum fechamento ainda.</Vazio>}
      <ul className="flex flex-col divide-y divide-borda">
        {lista.map((f) => (
          <li key={f.id}>
            <button type="button" onClick={() => setAberto(f.id)} className="flex min-h-12 w-full flex-wrap items-center gap-3 py-2 text-left text-sm hover:text-marca">
              <span className="flex-1">
                {f.period_start ? `${dataBR(f.period_start)} a ` : "Até "}
                {dataBR(f.period_end)}
                <span className="block text-xs text-texto-suave">
                  Fechado por {nomeMembro(equipe.data, f.closed_by)} em {dataHoraBR(f.closed_at)}
                  {f.notes && ` · ${f.notes}`}
                </span>
              </span>
              <strong>{dinheiro(f.total)}</strong>
            </button>
          </li>
        ))}
      </ul>
      {aberto && <DetalheFechamento id={aberto} aoFechar={() => setAberto(null)} />}
    </Cartao>
  );
}

function DetalheFechamento({ id, aoFechar }: { id: string; aoFechar: () => void }) {
  const detalhe = useQuery({
    queryKey: ["repasse", "fechamento", id],
    queryFn: async () => ok(await api.GET("/repasse/fechamentos/{settlement_id}", { params: { path: { settlement_id: id } } })),
  });
  const f = detalhe.data;
  return (
    <Modal titulo="Fechamento de repasse" aberto aoFechar={aoFechar} largura="max-w-3xl">
      {detalhe.isLoading && <Carregando />}
      {detalhe.error && <ErroCarga erro={detalhe.error} />}
      {f && (
        <div className="flex flex-col gap-3">
          <p className="text-sm">
            {f.period_start ? `${dataBR(f.period_start)} a ` : "Até "}
            {dataBR(f.period_end)} · <strong>{dinheiro(f.total)}</strong>
          </p>
          <TabelaLinhas linhas={f.lines} />
          <Botao variante="secundario" className="self-end" onClick={() => window.print()}>
            Imprimir
          </Botao>
        </div>
      )}
    </Modal>
  );
}
