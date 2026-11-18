import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import Modal from "../../components/Modal";
import { Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Selecao, Vazio } from "../../components/ui";
import { dataBR, dinheiro, hojeISO, mesAtual } from "../../lib/datas";
import { METODOS } from "../../lib/pagamento";

type Conta = Schemas["PayableOut"];
type Situacao = "" | "aberta" | "paga" | "cancelada";

/** Último dia do mês AAAA-MM. */
function fimDoMes(mes: string): string {
  const [a, m] = mes.split("-").map(Number);
  return new Date(Date.UTC(a, m, 0)).toISOString().slice(0, 10);
}

export default function ContasPagar() {
  const [mes, setMes] = useState(mesAtual());
  const [situacao, setSituacao] = useState<Situacao>("");
  const [nova, setNova] = useState(false);
  const [acao, setAcao] = useState<{ tipo: "pagar" | "cancelar"; conta: Conta } | null>(null);
  const contas = useQuery({
    queryKey: ["financeiro", "pagar", mes, situacao],
    queryFn: async () =>
      ok(
        await api.GET("/financeiro/pagar", {
          params: {
            query: {
              vencimento_de: mes ? `${mes}-01` : undefined,
              vencimento_ate: mes ? fimDoMes(mes) : undefined,
              situacao: situacao || undefined,
              limit: 500,
            },
          },
        }),
      ),
  });
  // Contas em atraso de meses anteriores continuam pedindo ação: busca à parte.
  const atrasadas = useQuery({
    queryKey: ["financeiro", "pagar", "atrasadas"],
    queryFn: async () =>
      ok(await api.GET("/financeiro/pagar", { params: { query: { situacao: "aberta", vencimento_ate: hojeISO(), limit: 500 } } })).filter(
        (c) => c.overdue,
      ),
  });
  const lista = contas.data ?? [];
  const soma = (f: (c: Conta) => boolean) => lista.filter(f).reduce((t, c) => t + Number(c.amount), 0);
  const atrasoTotal = (atrasadas.data ?? []).reduce((t, c) => t + Number(c.amount), 0);

  return (
    <div className="flex flex-col gap-4">
      {atrasadas.data && atrasadas.data.length > 0 && (
        <Aviso tom="perigo">
          {atrasadas.data.length} conta{atrasadas.data.length > 1 ? "s" : ""} em atraso, total {dinheiro(atrasoTotal)}.{" "}
          <button type="button" className="font-semibold underline" onClick={() => { setMes(""); setSituacao("aberta"); }}>
            Ver todas
          </button>
        </Aviso>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <Campo rotulo="Vencimento no mês" type="month" value={mes} onChange={(e) => setMes(e.target.value)} />
        <Selecao rotulo="Situação" value={situacao} onChange={(e) => setSituacao(e.target.value as Situacao)}>
          <option value="">Todas</option>
          <option value="aberta">Em aberto</option>
          <option value="paga">Pagas</option>
          <option value="cancelada">Canceladas</option>
        </Selecao>
        <Botao onClick={() => setNova(true)}>+ Nova conta</Botao>
      </div>
      {lista.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-3">
          <Resumo rotulo="Em aberto" valor={soma((c) => c.status === "aberta")} />
          <Resumo rotulo="Pago" valor={soma((c) => c.status === "paga")} />
          <Resumo rotulo="Em atraso" valor={soma((c) => c.overdue)} perigo />
        </div>
      )}
      {contas.isLoading && <Carregando />}
      {contas.error && <ErroCarga erro={contas.error} />}
      {contas.data && lista.length === 0 && (
        <Cartao>
          <Vazio>Nenhuma conta {mes ? "com vencimento neste mês" : "com esse filtro"}.</Vazio>
        </Cartao>
      )}
      <ul className="flex flex-col gap-2">
        {lista.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-borda bg-painel p-3">
            <div className="min-w-0 flex-1">
              <p className="font-semibold">
                {c.supplier}
                {c.category && <span className="font-normal text-texto-suave"> · {c.category}</span>}
              </p>
              <p className="text-xs text-texto-suave">
                Vence {dataBR(c.due_date)}
                {c.description && ` · ${c.description}`}
                {c.status === "paga" && ` · paga em ${dataBR(c.paid_on)}${c.paid_method ? ` (${METODOS[c.paid_method] ?? c.paid_method})` : ""}`}
                {c.status === "cancelada" && c.cancel_reason && ` · cancelada: ${c.cancel_reason}`}
              </p>
            </div>
            <p className={`font-semibold ${c.status === "cancelada" ? "text-texto-suave line-through" : ""}`}>{dinheiro(c.amount)}</p>
            {c.overdue ? (
              <Etiqueta tom="perigo">em atraso</Etiqueta>
            ) : (
              <Etiqueta tom={c.status === "paga" ? "sucesso" : c.status === "cancelada" ? "alerta" : "info"}>{c.status}</Etiqueta>
            )}
            {c.status === "aberta" && (
              <div className="flex gap-1">
                <Botao variante="secundario" className="min-h-9" onClick={() => setAcao({ tipo: "pagar", conta: c })}>
                  Pagar
                </Botao>
                <Botao variante="fantasma" className="min-h-9 px-2" onClick={() => setAcao({ tipo: "cancelar", conta: c })}>
                  Cancelar
                </Botao>
              </div>
            )}
          </li>
        ))}
      </ul>
      {nova && <NovaConta aoFechar={() => setNova(false)} />}
      {acao && <AcaoConta tipo={acao.tipo} conta={acao.conta} aoFechar={() => setAcao(null)} />}
    </div>
  );
}

function Resumo({ rotulo, valor, perigo = false }: { rotulo: string; valor: number; perigo?: boolean }) {
  return (
    <div className="rounded-xl border border-borda bg-painel p-3">
      <p className="text-xs text-texto-suave">{rotulo}</p>
      <p className={`text-lg font-bold ${perigo && valor > 0 ? "text-perigo" : ""}`}>{dinheiro(valor)}</p>
    </div>
  );
}

function NovaConta({ aoFechar }: { aoFechar: () => void }) {
  const cliente = useQueryClient();
  const [fornecedor, setFornecedor] = useState("");
  const [categoria, setCategoria] = useState("");
  const [descricao, setDescricao] = useState("");
  const [vencimento, setVencimento] = useState(hojeISO());
  const [valor, setValor] = useState("");
  const salvar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/financeiro/pagar", {
          body: {
            supplier: fornecedor.trim(),
            category: categoria.trim() || null,
            description: descricao.trim() || null,
            due_date: vencimento,
            amount: valor.trim().replace(",", "."),
          },
        }),
      ),
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["financeiro", "pagar"] });
      aoFechar();
    },
  });
  return (
    <Modal titulo="Nova conta a pagar" aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        <Campo rotulo="Fornecedor ou favorecido" value={fornecedor} onChange={(e) => setFornecedor(e.target.value)} placeholder="Dental Sul" />
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo="Categoria" value={categoria} onChange={(e) => setCategoria(e.target.value)} placeholder="Material, aluguel, laboratório…" />
          <Campo rotulo="Valor (R$)" inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} />
          <Campo rotulo="Vencimento" type="date" value={vencimento} onChange={(e) => setVencimento(e.target.value)} />
          <Campo rotulo="Descrição" value={descricao} onChange={(e) => setDescricao(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao onClick={() => salvar.mutate()} carregando={salvar.isPending} disabled={!fornecedor.trim() || !valor.trim() || !vencimento}>
            Salvar
          </Botao>
        </div>
      </div>
    </Modal>
  );
}

function AcaoConta({ tipo, conta, aoFechar }: { tipo: "pagar" | "cancelar"; conta: Conta; aoFechar: () => void }) {
  const cliente = useQueryClient();
  const [metodo, setMetodo] = useState("pix");
  const [data, setData] = useState(hojeISO());
  const [motivo, setMotivo] = useState("");
  const salvar = useMutation({
    mutationFn: async () => {
      const path = { payable_id: conta.id };
      return tipo === "pagar"
        ? ok(await api.POST("/financeiro/pagar/{payable_id}/pagar", { params: { path }, body: { method: metodo as Schemas["PaymentMethod"], paid_on: data } }))
        : ok(await api.POST("/financeiro/pagar/{payable_id}/cancelar", { params: { path }, body: { reason: motivo.trim() } }));
    },
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["financeiro", "pagar"] });
      aoFechar();
    },
  });
  return (
    <Modal titulo={tipo === "pagar" ? "Registrar pagamento" : "Cancelar conta"} aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        <p className="text-sm">
          {conta.supplier}: <strong>{dinheiro(conta.amount)}</strong>, vence {dataBR(conta.due_date)}.
        </p>
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        {tipo === "pagar" ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Selecao rotulo="Forma de pagamento" value={metodo} onChange={(e) => setMetodo(e.target.value)}>
              {Object.entries(METODOS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </Selecao>
            <Campo rotulo="Pago em" type="date" max={hojeISO()} value={data} onChange={(e) => setData(e.target.value)} />
          </div>
        ) : (
          <Campo rotulo="Motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Lançada em duplicidade" />
        )}
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Voltar
          </Botao>
          <Botao
            variante={tipo === "pagar" ? "primario" : "perigo"}
            onClick={() => salvar.mutate()}
            carregando={salvar.isPending}
            disabled={tipo === "cancelar" ? !motivo.trim() : !data}
          >
            {tipo === "pagar" ? "Confirmar pagamento" : "Cancelar conta"}
          </Botao>
        </div>
      </div>
    </Modal>
  );
}
