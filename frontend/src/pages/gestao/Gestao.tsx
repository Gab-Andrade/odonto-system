import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import { GESTAO, temPapel, useSessao } from "../../auth/sessao";
import { Abas, Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Selecao, Titulo } from "../../components/ui";
import { dataBR, dinheiro, mesAtual } from "../../lib/datas";
import { useDentistas } from "../../lib/equipe";
import Barras from "./Barras";

type Metricas = Schemas["MonthMetricsOut"];
type Aba = "geral" | "equipe" | "tendencias" | "metas" | "meu";

const NOME_METRICA: Record<string, string> = {
  recebido: "Recebido",
  producao: "Produção",
  procedimentos: "Procedimentos",
  aprovado: "Valor aprovado",
};
const MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const rotuloMes = (iso: string) => `${MES[Number(iso.slice(5, 7)) - 1]}/${iso.slice(2, 4)}`;
const pct = (v?: string | null) => (v === null || v === undefined ? "—" : `${v}%`);

function Variacao({ v }: { v?: string | null }) {
  if (v === null || v === undefined) return <span className="text-xs text-texto-suave">sem base</span>;
  const n = Number(v);
  return (
    <span className={`text-xs font-semibold ${n >= 0 ? "text-sucesso" : "text-perigo"}`}>
      {n >= 0 ? "▲" : "▼"} {Math.abs(n)}% vs mês anterior
    </span>
  );
}

function Indicador({ rotulo, valor, variacao, dica }: { rotulo: string; valor: string; variacao?: string | null; dica?: string }) {
  return (
    <Cartao>
      <p className="text-xs text-texto-suave" title={dica}>
        {rotulo}
      </p>
      <p className="text-2xl font-bold">{valor}</p>
      {variacao !== undefined && <Variacao v={variacao} />}
    </Cartao>
  );
}

export default function Gestao() {
  const { papel } = useSessao();
  const gestor = temPapel(papel, ...GESTAO);
  const abas: { id: Aba; rotulo: string }[] = gestor
    ? [
        { id: "geral", rotulo: "Visão geral" },
        { id: "equipe", rotulo: "Equipe" },
        { id: "tendencias", rotulo: "Tendências" },
        { id: "metas", rotulo: "Metas" },
        ...(papel === "admin" ? [{ id: "meu" as Aba, rotulo: "Meu desempenho" }] : []),
      ]
    : [{ id: "meu", rotulo: "Meu desempenho" }];
  const [aba, setAba] = useState<Aba>(abas[0].id);
  const [mes, setMes] = useState(mesAtual());

  return (
    <div>
      <Titulo acoes={<Campo rotulo="Mês" type="month" value={mes} onChange={(e) => e.target.value && setMes(e.target.value)} />}>
        Gestão
      </Titulo>
      <Abas abas={abas} atual={aba} aoMudar={setAba} />
      {aba === "geral" && <VisaoGeral mes={mes} />}
      {aba === "equipe" && <Equipe mes={mes} />}
      {aba === "tendencias" && <Tendencias ate={mes} />}
      {aba === "metas" && <Metas mes={mes} />}
      {aba === "meu" && <MeuDesempenho mes={mes} />}
    </div>
  );
}

function VisaoGeral({ mes }: { mes: string }) {
  const q = useQuery({
    queryKey: ["painel", "geral", mes],
    queryFn: async () => ok(await api.GET("/painel/visao-geral", { params: { query: { mes } } })),
  });
  if (q.isLoading) return <Carregando />;
  if (q.error) return <ErroCarga erro={q.error} />;
  const v = q.data!;
  const c = v.comparison ?? {};
  return (
    <div className="flex flex-col gap-4">
      {v.alerts && v.alerts.total > 0 && (
        <Aviso tom="alerta">
          {v.alerts.total} alerta(s) pedem atenção — veja em <a href="/alertas" className="font-semibold underline">Alertas</a>.
        </Aviso>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Indicador rotulo="Recebido no mês" valor={dinheiro(v.revenue.received)} variacao={c.recebido} dica="Recebimentos com data no mês, já com estornos." />
        <Indicador rotulo="Previsto no mês" valor={dinheiro(v.revenue.expected)} dica="Contas a receber que vencem no mês." />
        <Indicador rotulo="Em atraso" valor={dinheiro(v.overdue.amount)} dica={`${v.overdue.count} conta(s) vencida(s)`} />
        <Indicador rotulo="A pagar vencido" valor={dinheiro(v.payables.overdue_amount)} dica={`e ${dinheiro(v.payables.soon_amount)} nos próximos 7 dias`} />
        <Indicador rotulo="Consultas hoje" valor={String(v.agenda.total)} dica={`${v.agenda.confirmado} confirmadas, ${v.agenda.agendado} sem confirmação`} />
        <Indicador rotulo="Orçamentos aguardando" valor={String(v.quotes.awaiting)} dica={`${v.quotes.awaiting_stale} há mais de 7 dias`} />
        <Indicador rotulo="Aprovado no mês" valor={dinheiro(v.quotes.approved_value_in_month)} variacao={c.aprovado} />
        <Indicador rotulo="Estoque" valor={`${v.stock.below_minimum} abaixo do mínimo`} dica={`${v.stock.expired_lots} lote(s) vencido(s), ${v.stock.expiring_lots} vencendo`} />
      </div>
      {(v.goals ?? []).length > 0 && <ListaMetas metas={v.goals ?? []} />}
      <Cartao titulo="Produção por dentista no mês">
        <ul className="divide-y divide-borda">
          {v.production.length === 0 && <li className="py-2 text-sm text-texto-suave">Nenhum procedimento realizado no mês.</li>}
          {v.production.map((p) => (
            <li key={p.dentist_id} className="flex justify-between py-2 text-sm">
              <span>{p.dentist_name ?? "—"}</span>
              <span>
                {p.procedures} proc. · <strong>{dinheiro(p.value)}</strong>
              </span>
            </li>
          ))}
        </ul>
      </Cartao>
      <p className="text-xs text-texto-suave">
        Só números agregados (sem dados de pacientes). Passe o dedo/mouse sobre um indicador para ver de onde ele vem.
      </p>
    </div>
  );
}

function ListaMetas({ metas }: { metas: Schemas["GoalOut"][] }) {
  return (
    <Cartao titulo="Metas do mês">
      <ul className="flex flex-col gap-3">
        {metas.map((m) => {
          const p = Math.min(Number(m.pct ?? 0), 100);
          const fmt = m.metric === "procedimentos" ? (x?: string | null) => String(Number(x ?? 0)) : dinheiro;
          return (
            <li key={m.id}>
              <div className="flex justify-between text-sm">
                <span>{NOME_METRICA[m.metric]}</span>
                <span>
                  {fmt(m.achieved)} de {fmt(m.target)} ({pct(m.pct)})
                </span>
              </div>
              <div className="mt-1 h-3 overflow-hidden rounded-full bg-fundo" role="progressbar" aria-valuenow={p} aria-valuemin={0} aria-valuemax={100}>
                <div className="h-full rounded-full bg-marca" style={{ width: `${p}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </Cartao>
  );
}

function Equipe({ mes }: { mes: string }) {
  const q = useQuery({
    queryKey: ["painel", "equipe", mes],
    queryFn: async () => ok(await api.GET("/painel/equipe", { params: { query: { mes } } })),
  });
  if (q.isLoading) return <Carregando />;
  if (q.error) return <ErroCarga erro={q.error} />;
  return (
    <Cartao>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-borda text-left text-xs text-texto-suave">
              <th className="py-2">Dentista</th>
              <th className="text-right">Produção</th>
              <th className="text-right">Proc.</th>
              <th className="text-right">Atend.</th>
              <th className="text-right">Conversão</th>
              <th className="text-right">Ticket médio</th>
              <th className="text-right">Consultas</th>
              <th className="text-right">Faltas</th>
              <th className="text-right">Metas</th>
            </tr>
          </thead>
          <tbody>
            {q.data!.members.map((m) => (
              <tr key={m.dentist_id} className="border-b border-borda/60">
                <td className="py-2 font-medium">{m.name}</td>
                <td className="text-right">{dinheiro(m.metrics.producao)}</td>
                <td className="text-right">{m.metrics.procedimentos}</td>
                <td className="text-right">{m.metrics.atendimentos}</td>
                <td className="text-right">{pct(m.metrics.conversao_pct)}</td>
                <td className="text-right">{dinheiro(m.metrics.ticket_medio)}</td>
                <td className="text-right">{m.metrics.consultas}</td>
                <td className="text-right">
                  {m.metrics.faltas} ({pct(m.metrics.taxa_faltas_pct)})
                </td>
                <td className="text-right">{m.goals.map((g) => `${NOME_METRICA[g.metric]} ${pct(g.pct)}`).join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-texto-suave">
        Conversão = orçamentos aprovados ÷ decididos no mês. Ticket médio = valor aprovado ÷ orçamentos aprovados. Acompanhamento, não vigilância: a auditoria fica restrita.
      </p>
    </Cartao>
  );
}

function SerieMensal({ meses }: { meses: Schemas["TrendPointOut"][] }) {
  const ultimo = meses[meses.length - 1];
  const serie = (k: keyof Metricas) => meses.map((m) => ({ rotulo: rotuloMes(m.metrics.month), valor: Number(m.metrics[k] ?? 0) }));
  const inteiro = (v: number) => String(Math.round(v));
  const real = (v: number) => dinheiro(v).replace(/,\d\d$/, "");
  const graficos: [keyof Metricas, string, (v: number) => string][] = [
    ["recebido", "Recebido", real],
    ["producao", "Produção", real],
    ["aprovado", "Valor aprovado", real],
    ["procedimentos", "Procedimentos", inteiro],
    ["consultas", "Consultas", inteiro],
    ["faltas", "Faltas", inteiro],
  ];
  const [tabela, setTabela] = useState(false);
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {graficos
          .filter(([k]) => ultimo?.metrics[k] !== null)
          .map(([k, t, f]) => (
            <Cartao key={k}>
              <Barras titulo={t} pontos={serie(k)} formatar={f} />
              {ultimo && <Variacao v={ultimo.variation_pct[k as string]} />}
            </Cartao>
          ))}
      </div>
      <Botao variante="fantasma" className="self-start" onClick={() => setTabela(!tabela)}>
        {tabela ? "Esconder tabela" : "Ver como tabela"}
      </Botao>
      {tabela && (
        <Cartao>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-borda text-left text-xs text-texto-suave">
                  <th className="py-2">Mês</th>
                  {graficos.map(([k, t]) => (
                    <th key={k} className="text-right">
                      {t}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {meses.map((m) => (
                  <tr key={m.metrics.month} className="border-b border-borda/60">
                    <td className="py-2">{rotuloMes(m.metrics.month)}</td>
                    {graficos.map(([k, , f]) => (
                      <td key={k} className="text-right">
                        {m.metrics[k] === null ? "—" : f(Number(m.metrics[k]))}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Cartao>
      )}
    </div>
  );
}

function Tendencias({ ate }: { ate: string }) {
  const dentistas = useDentistas();
  const [dentista, setDentista] = useState("");
  const q = useQuery({
    queryKey: ["painel", "tendencias", ate, dentista],
    queryFn: async () =>
      ok(await api.GET("/painel/tendencias", { params: { query: { ate, meses: 6, dentista_id: dentista || undefined } } })),
  });
  return (
    <div className="flex flex-col gap-4">
      <Selecao rotulo="Dentista" className="max-w-xs" value={dentista} onChange={(e) => setDentista(e.target.value)}>
        <option value="">Clínica inteira</option>
        {dentistas.data?.map((d) => (
          <option key={d.user_id} value={d.user_id}>
            {d.full_name}
          </option>
        ))}
      </Selecao>
      {q.isLoading && <Carregando />}
      {q.error && <ErroCarga erro={q.error} />}
      {q.data && <SerieMensal meses={q.data.months} />}
    </div>
  );
}

function Metas({ mes }: { mes: string }) {
  const cliente = useQueryClient();
  const dentistas = useDentistas();
  const [metrica, setMetrica] = useState("producao");
  const [dentista, setDentista] = useState("");
  const [valor, setValor] = useState("");
  const q = useQuery({
    queryKey: ["painel", "metas", mes],
    queryFn: async () => ok(await api.GET("/painel/metas", { params: { query: { mes } } })),
  });
  const salvar = useMutation({
    mutationFn: async () =>
      ok(
        await api.PUT("/painel/metas", {
          body: { month: `${mes}-01`, metric: metrica, dentist_id: dentista || null, target: valor.replace(",", ".") },
        }),
      ),
    onSuccess: () => {
      setValor("");
      cliente.invalidateQueries({ queryKey: ["painel"] });
    },
  });
  const remover = useMutation({
    mutationFn: async (id: string) => ok(await api.DELETE("/painel/metas/{goal_id}", { params: { path: { goal_id: id } } })),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["painel"] }),
  });
  const nome = (id?: string | null) => (id ? (dentistas.data?.find((d) => d.user_id === id)?.full_name ?? "—") : "Clínica");

  return (
    <div className="flex flex-col gap-4">
      <Cartao titulo={`Definir meta de ${dataBR(`${mes}-01`).slice(3)}`}>
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        <div className="flex flex-wrap items-end gap-3">
          <Selecao rotulo="Indicador" value={metrica} onChange={(e) => setMetrica(e.target.value)}>
            {Object.entries(NOME_METRICA).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Selecao>
          <Selecao rotulo="De quem" value={dentista} onChange={(e) => setDentista(e.target.value)} disabled={metrica === "recebido"}>
            <option value="">Clínica</option>
            {dentistas.data?.map((d) => (
              <option key={d.user_id} value={d.user_id}>
                {d.full_name}
              </option>
            ))}
          </Selecao>
          <Campo rotulo={metrica === "procedimentos" ? "Quantidade" : "Valor (R$)"} inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} />
          <Botao onClick={() => salvar.mutate()} carregando={salvar.isPending} disabled={!valor}>
            Salvar meta
          </Botao>
        </div>
        <p className="mt-2 text-xs text-texto-suave">Metas são opcionais. Salvar de novo o mesmo indicador substitui o valor.</p>
      </Cartao>
      {q.isLoading && <Carregando />}
      {q.error && <ErroCarga erro={q.error} />}
      {q.data && (
        <Cartao titulo="Metas do mês">
          {q.data.length === 0 && <p className="text-sm text-texto-suave">Nenhuma meta definida.</p>}
          <ul className="divide-y divide-borda">
            {q.data.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                <span className="flex-1">
                  {NOME_METRICA[m.metric]} · {nome(m.dentist_id)}
                </span>
                <span>
                  {m.metric === "procedimentos" ? Number(m.achieved ?? 0) : dinheiro(m.achieved)} de{" "}
                  {m.metric === "procedimentos" ? Number(m.target) : dinheiro(m.target)} ({pct(m.pct)})
                </span>
                <Botao variante="fantasma" onClick={() => remover.mutate(m.id)}>
                  Remover
                </Botao>
              </li>
            ))}
          </ul>
        </Cartao>
      )}
    </div>
  );
}

function MeuDesempenho({ mes }: { mes: string }) {
  const q = useQuery({
    queryKey: ["painel", "meu", mes],
    queryFn: async () => ok(await api.GET("/painel/meu-desempenho", { params: { query: { mes } } })),
  });
  const t = useQuery({
    queryKey: ["painel", "minha-tendencia", mes],
    queryFn: async () => ok(await api.GET("/painel/minha-tendencia", { params: { query: { ate: mes, meses: 6 } } })),
  });
  if (q.isLoading) return <Carregando />;
  if (q.error) return <ErroCarga erro={q.error} />;
  const v = q.data!;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Indicador rotulo="Produção no mês" valor={dinheiro(v.production.value)} variacao={v.comparison?.producao} />
        <Indicador rotulo="Procedimentos" valor={String(v.production.procedures)} variacao={v.comparison?.procedimentos} />
        <Indicador rotulo="Atendimentos" valor={String(v.encounters)} variacao={v.comparison?.atendimentos} />
        <Indicador rotulo="Último repasse" valor={v.last_settlement ? dinheiro(v.last_settlement.total) : "—"} dica={v.last_settlement ? `até ${dataBR(v.last_settlement.period_end)}` : undefined} />
        <Indicador rotulo="Consultas hoje" valor={String(v.agenda_today.total)} />
        <Indicador rotulo="Orçamentos aguardando" valor={String(v.quotes.awaiting)} />
        <Indicador rotulo="Aprovado no mês" valor={dinheiro(v.quotes.approved_value_in_month)} />
        <Indicador rotulo="Meus alertas" valor={String(v.alerts?.total ?? 0)} />
      </div>
      {(v.goals ?? []).length > 0 && <ListaMetas metas={v.goals ?? []} />}
      {t.data && <SerieMensal meses={t.data.months} />}
    </div>
  );
}
