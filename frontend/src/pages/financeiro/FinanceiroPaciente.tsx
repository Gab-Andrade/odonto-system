import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import Modal from "../../components/Modal";
import { Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Selecao, Vazio } from "../../components/ui";
import { dataBR, dinheiro } from "../../lib/datas";

type Conta = Schemas["ReceivableOut"];

const METODOS: Record<string, string> = {
  pix: "Pix",
  dinheiro: "Dinheiro",
  debito: "Débito",
  credito: "Crédito",
  boleto: "Boleto",
  transferencia: "Transferência",
};
const TOM: Record<string, "info" | "alerta" | "perigo" | "sucesso"> = {
  aberta: "info",
  parcial: "alerta",
  vencida: "perigo",
  paga: "sucesso",
  cancelada: "perigo",
};

/** Extrato do paciente e registro de pagamento (caixa: admin, gestor e recepção). */
export default function FinanceiroPaciente({ pacienteId }: { pacienteId: string }) {
  const [pagar, setPagar] = useState<Conta | null>(null);
  const extrato = useQuery({
    queryKey: ["financeiro", pacienteId],
    queryFn: async () =>
      ok(
        await api.GET("/financeiro/pacientes/{patient_id}/extrato", {
          params: { path: { patient_id: pacienteId } },
        }),
      ),
  });

  if (extrato.isLoading) return <Carregando />;
  if (extrato.error) return <ErroCarga erro={extrato.error} />;
  const e = extrato.data!;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-4">
        {[
          ["Total", e.total],
          ["Pago", e.paid],
          ["Em aberto", e.balance],
          ["Vencido", e.overdue],
        ].map(([r, v]) => (
          <Cartao key={r}>
            <p className="text-xs text-texto-suave">{r}</p>
            <p className={`text-xl font-bold ${r === "Vencido" && Number(v) > 0 ? "text-perigo" : ""}`}>{dinheiro(v)}</p>
          </Cartao>
        ))}
      </div>
      <Cartao titulo="Contas a receber">
        {e.receivables.length === 0 && <Vazio>Nenhuma conta. Parcele um orçamento aprovado na aba Planos.</Vazio>}
        <ul className="divide-y divide-borda">
          {e.receivables.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{c.description}</p>
                <p className="text-xs text-texto-suave">
                  Vence {dataBR(c.due_date)} · {dinheiro(c.amount)} · pago {dinheiro(c.paid)}
                </p>
              </div>
              <Etiqueta tom={TOM[c.status] ?? "info"}>{c.status}</Etiqueta>
              {Number(c.balance) > 0 && !c.cancelled_at && (
                <Botao variante="secundario" onClick={() => setPagar(c)}>
                  Receber
                </Botao>
              )}
            </li>
          ))}
        </ul>
      </Cartao>
      {pagar && <Receber conta={pagar} pacienteId={pacienteId} aoFechar={() => setPagar(null)} />}
    </div>
  );
}

function Receber({ conta, pacienteId, aoFechar }: { conta: Conta; pacienteId: string; aoFechar: () => void }) {
  const cliente = useQueryClient();
  const [valor, setValor] = useState(String(conta.balance));
  const [metodo, setMetodo] = useState("pix");
  const [taxa, setTaxa] = useState("0");
  const salvar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/financeiro/receber/{receivable_id}/pagamentos", {
          params: { path: { receivable_id: conta.id } },
          body: {
            amount: valor.replace(",", "."),
            method: metodo as Schemas["PaymentMethod"],
            fee_pct: taxa.replace(",", ".") || "0",
          },
        }),
      ),
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["financeiro", pacienteId] });
      aoFechar();
    },
  });
  return (
    <Modal titulo="Registrar recebimento" aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        <p className="text-sm">
          {conta.description} · em aberto {dinheiro(conta.balance)}
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Campo rotulo="Valor (R$)" inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} />
          <Selecao rotulo="Forma" value={metodo} onChange={(e) => setMetodo(e.target.value)}>
            {Object.entries(METODOS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Selecao>
          <Campo rotulo="Taxa (%)" inputMode="decimal" value={taxa} onChange={(e) => setTaxa(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao onClick={() => salvar.mutate()} carregando={salvar.isPending}>
            Registrar
          </Botao>
        </div>
      </div>
    </Modal>
  );
}
