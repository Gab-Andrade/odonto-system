import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import { GESTAO, temPapel, useSessao } from "../../auth/sessao";
import Modal from "../../components/Modal";
import {
  Abas,
  Aviso,
  Botao,
  Campo,
  Cartao,
  Carregando,
  ErroCarga,
  Etiqueta,
  Selecao,
  Titulo,
  Vazio,
} from "../../components/ui";
import { dataBR, dataHoraBR, dinheiro, hojeISO } from "../../lib/datas";
import { nomeMembro, useEquipe } from "../../lib/equipe";

/**
 * Estoque: saldos por material e lote (com validade), entradas, saídas e inventário;
 * cadastro de materiais e livro de movimentos para admin e gestor. A ASB dá entrada e
 * saída, mas não vê custo; dentista só consulta.
 */

type Saldo = Schemas["app__modules__estoque__schemas__StockOut"];
type Lote = Schemas["LotOut"];
type Material = Schemas["MaterialCostOut"];
type Aba = "saldos" | "materiais" | "movimentos";

const qtd = (v: string | number | null | undefined) =>
  v === null || v === undefined ? "—" : new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 }).format(Number(v));
const decimal = (v: string) => v.trim().replace(",", ".");

const VALIDADE: Record<string, { rotulo: string; tom: "perigo" | "alerta" | "info" | "sucesso" }> = {
  vencido: { rotulo: "vencido", tom: "perigo" },
  vence_em_breve: { rotulo: "vence em breve", tom: "alerta" },
  sem_validade: { rotulo: "sem validade", tom: "info" },
  ok: { rotulo: "na validade", tom: "sucesso" },
};

export default function Estoque() {
  const papel = useSessao((s) => s.papel);
  const gestao = temPapel(papel, ...GESTAO);
  const [aba, setAba] = useState<Aba>("saldos");
  return (
    <div>
      <Titulo>Estoque</Titulo>
      {gestao && (
        <Abas
          abas={[
            { id: "saldos", rotulo: "Saldos e lotes" },
            { id: "materiais", rotulo: "Materiais" },
            { id: "movimentos", rotulo: "Movimentos" },
          ]}
          atual={aba}
          aoMudar={setAba}
        />
      )}
      {aba === "saldos" && <Saldos />}
      {aba === "materiais" && gestao && <Materiais />}
      {aba === "movimentos" && gestao && <Movimentos />}
    </div>
  );
}

function useMateriais(incluirInativos = false) {
  return useQuery({
    queryKey: ["estoque", "materiais", incluirInativos],
    queryFn: async () => ok(await api.GET("/estoque/materiais", { params: { query: { incluir_inativos: incluirInativos } } })),
  });
}

// ---------- saldos ----------

type Acao = { tipo: "entrada"; materialId?: string } | { tipo: "saida" | "ajuste"; lote: Lote; saldo: Saldo };

function Saldos() {
  const papel = useSessao((s) => s.papel);
  const movimenta = temPapel(papel, "admin", "gestor", "asb");
  const [soAlertas, setSoAlertas] = useState(false);
  const [busca, setBusca] = useState("");
  const [acao, setAcao] = useState<Acao | null>(null);
  const saldos = useQuery({
    queryKey: ["estoque", "saldos", soAlertas],
    queryFn: async () => ok(await api.GET("/estoque/saldos", { params: { query: { somente_alertas: soAlertas } } })),
  });
  const termo = busca.trim().toLowerCase();
  const lista = (saldos.data ?? []).filter((s) => !termo || s.name.toLowerCase().includes(termo));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <Campo rotulo="Buscar material" value={busca} onChange={(e) => setBusca(e.target.value)} className="min-w-48 flex-1" />
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" className="size-5 accent-marca" checked={soAlertas} onChange={(e) => setSoAlertas(e.target.checked)} />
          Só o que pede atenção
        </label>
        {movimenta && <Botao onClick={() => setAcao({ tipo: "entrada" })}>+ Entrada de material</Botao>}
      </div>
      {saldos.isLoading && <Carregando />}
      {saldos.error && <ErroCarga erro={saldos.error} />}
      {saldos.data && lista.length === 0 && (
        <Cartao>
          <Vazio>
            {soAlertas
              ? "Nada abaixo do mínimo nem vencendo."
              : saldos.data.length === 0
                ? "Nenhum material cadastrado."
                : "Nenhum material com esse nome."}
          </Vazio>
        </Cartao>
      )}
      <ul className="flex flex-col gap-3">
        {lista.map((s) => (
          <li key={s.material_id}>
            <CartaoSaldo saldo={s} movimenta={movimenta} aoAgir={setAcao} />
          </li>
        ))}
      </ul>
      {acao?.tipo === "entrada" && <Entrada materialId={acao.materialId} aoFechar={() => setAcao(null)} />}
      {acao && acao.tipo !== "entrada" && (
        <SaidaOuAjuste tipo={acao.tipo} lote={acao.lote} saldo={acao.saldo} aoFechar={() => setAcao(null)} />
      )}
    </div>
  );
}

function CartaoSaldo({ saldo: s, movimenta, aoAgir }: { saldo: Saldo; movimenta: boolean; aoAgir: (a: Acao) => void }) {
  const papel = useSessao((x) => x.papel);
  const gestao = temPapel(papel, ...GESTAO);
  const venc = s.lots.some((l) => l.expiry === "vencido");
  const breve = s.lots.some((l) => l.expiry === "vence_em_breve");
  return (
    <Cartao
      titulo={
        <span className="flex flex-wrap items-center gap-2">
          {s.name}
          {s.below_minimum && <Etiqueta tom="perigo">abaixo do mínimo</Etiqueta>}
          {venc && <Etiqueta tom="perigo">lote vencido</Etiqueta>}
          {!venc && breve && <Etiqueta tom="alerta">vence em breve</Etiqueta>}
        </span>
      }
      acoes={
        movimenta && (
          <Botao variante="secundario" onClick={() => aoAgir({ tipo: "entrada", materialId: s.material_id })}>
            + Entrada
          </Botao>
        )
      }
    >
      <p className="text-sm">
        Saldo: <strong>{qtd(s.balance)}</strong> {s.unit}
        <span className="text-texto-suave">{s.min_quantity !== null && ` · mínimo ${qtd(s.min_quantity)} ${s.unit}`}</span>
      </p>
      {s.lots.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="text-left text-xs text-texto-suave">
              <tr>
                <th className="py-1 pr-3 font-medium">Lote</th>
                <th className="py-1 pr-3 font-medium">Validade</th>
                <th className="py-1 pr-3 font-medium">Recebido</th>
                <th className="py-1 pr-3 text-right font-medium">Saldo</th>
                {gestao && <th className="py-1 pr-3 text-right font-medium">Custo un.</th>}
                {movimenta && <th className="py-1" />}
              </tr>
            </thead>
            <tbody>
              {s.lots.map((l) => {
                const v = VALIDADE[l.expiry] ?? VALIDADE.ok;
                return (
                  <tr key={l.id} className="border-t border-borda">
                    <td className="py-2 pr-3">
                      {l.lot_code || <span className="text-texto-suave">sem código</span>}
                      {l.supplier && <span className="block text-xs text-texto-suave">{l.supplier}</span>}
                    </td>
                    <td className="py-2 pr-3">
                      {l.expires_on ? dataBR(l.expires_on) : "—"} <Etiqueta tom={v.tom}>{v.rotulo}</Etiqueta>
                    </td>
                    <td className="py-2 pr-3">{dataBR(l.received_on)}</td>
                    <td className="py-2 pr-3 text-right font-semibold">{qtd(l.balance)}</td>
                    {gestao && <td className="py-2 pr-3 text-right">{dinheiro(l.unit_cost)}</td>}
                    {movimenta && (
                      <td className="py-1 text-right whitespace-nowrap">
                        <Botao variante="fantasma" className="min-h-9 px-2" onClick={() => aoAgir({ tipo: "saida", lote: l, saldo: s })}>
                          Saída
                        </Botao>
                        {gestao && (
                          <Botao variante="fantasma" className="min-h-9 px-2" onClick={() => aoAgir({ tipo: "ajuste", lote: l, saldo: s })}>
                            Inventário
                          </Botao>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Cartao>
  );
}

function Entrada({ materialId, aoFechar }: { materialId?: string; aoFechar: () => void }) {
  const papel = useSessao((s) => s.papel);
  const informaCusto = temPapel(papel, ...GESTAO);
  const cliente = useQueryClient();
  const materiais = useMateriais();
  const [material, setMaterial] = useState(materialId ?? "");
  const [quantidade, setQuantidade] = useState("");
  const [custo, setCusto] = useState("");
  const [lote, setLote] = useState("");
  const [validade, setValidade] = useState("");
  const [fornecedor, setFornecedor] = useState("");
  const [recebido, setRecebido] = useState(hojeISO());
  const unidade = materiais.data?.find((m) => m.id === material)?.unit;
  const salvar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/estoque/entradas", {
          body: {
            material_id: material,
            quantity: decimal(quantidade),
            unit_cost: informaCusto ? decimal(custo) : null,
            lot_code: lote.trim() || null,
            expires_on: validade || null,
            supplier: fornecedor.trim() || null,
            received_on: recebido || null,
          },
        }),
      ),
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["estoque"] });
      aoFechar();
    },
  });
  const pronto = material && quantidade.trim() && (!informaCusto || custo.trim());
  return (
    <Modal titulo="Entrada de material" aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        <Selecao rotulo="Material" value={material} onChange={(e) => setMaterial(e.target.value)}>
          <option value="">— escolha —</option>
          {materiais.data?.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name} ({m.unit})
            </option>
          ))}
        </Selecao>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo={`Quantidade${unidade ? ` (${unidade})` : ""}`} inputMode="decimal" value={quantidade} onChange={(e) => setQuantidade(e.target.value)} />
          {informaCusto && (
            <Campo rotulo="Custo por unidade (R$)" inputMode="decimal" value={custo} onChange={(e) => setCusto(e.target.value)} dica="Recalcula o custo médio do material." />
          )}
          <Campo rotulo="Código do lote" value={lote} onChange={(e) => setLote(e.target.value)} />
          <Campo rotulo="Validade" type="date" value={validade} onChange={(e) => setValidade(e.target.value)} />
          <Campo rotulo="Fornecedor" value={fornecedor} onChange={(e) => setFornecedor(e.target.value)} />
          <Campo rotulo="Recebido em" type="date" max={hojeISO()} value={recebido} onChange={(e) => setRecebido(e.target.value)} />
        </div>
        {!informaCusto && <p className="text-xs text-texto-suave">O lote entra com o custo atual do material.</p>}
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao onClick={() => salvar.mutate()} carregando={salvar.isPending} disabled={!pronto}>
            Registrar entrada
          </Botao>
        </div>
      </div>
    </Modal>
  );
}

function SaidaOuAjuste({ tipo, lote, saldo, aoFechar }: { tipo: "saida" | "ajuste"; lote: Lote; saldo: Saldo; aoFechar: () => void }) {
  const cliente = useQueryClient();
  const [quantidade, setQuantidade] = useState(tipo === "ajuste" ? String(Number(lote.balance)) : "");
  const [motivo, setMotivo] = useState(tipo === "saida" && lote.expiry === "vencido" ? "Lote vencido" : "");
  const salvar = useMutation({
    mutationFn: async () =>
      tipo === "saida"
        ? ok(await api.POST("/estoque/saidas", { body: { lot_id: lote.id, quantity: decimal(quantidade), reason: motivo.trim() } }))
        : ok(await api.POST("/estoque/ajustes", { body: { lot_id: lote.id, counted_quantity: decimal(quantidade), reason: motivo.trim() } })),
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["estoque"] });
      aoFechar();
    },
  });
  const nomeLote = lote.lot_code ? `lote ${lote.lot_code}` : "lote sem código";
  return (
    <Modal titulo={tipo === "saida" ? "Saída de material" : "Inventário do lote"} aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        <p className="text-sm">
          {saldo.name}, {nomeLote}: saldo atual <strong>{qtd(lote.balance)}</strong> {saldo.unit}.
        </p>
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        <Campo
          rotulo={tipo === "saida" ? `Quantidade que sai (${saldo.unit})` : `Quantidade contada (${saldo.unit})`}
          inputMode="decimal"
          value={quantidade}
          onChange={(e) => setQuantidade(e.target.value)}
          dica={tipo === "ajuste" ? "O sistema grava a diferença para o saldo atual." : "Uso em paciente sai sozinho ao realizar o procedimento."}
        />
        <Campo
          rotulo="Motivo"
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          placeholder={tipo === "saida" ? "Perda, vencido, uso avulso…" : "Contagem mensal"}
        />
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao
            variante={tipo === "saida" ? "perigo" : "primario"}
            onClick={() => salvar.mutate()}
            carregando={salvar.isPending}
            disabled={!quantidade.trim() || !motivo.trim()}
          >
            {tipo === "saida" ? "Registrar saída" : "Salvar contagem"}
          </Botao>
        </div>
      </div>
    </Modal>
  );
}

// ---------- materiais ----------

function Materiais() {
  const [inativos, setInativos] = useState(false);
  const [editando, setEditando] = useState<Material | "novo" | null>(null);
  const materiais = useMateriais(inativos);
  const lista = (materiais.data ?? []) as Material[];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Botao onClick={() => setEditando("novo")}>+ Novo material</Botao>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" className="size-5 accent-marca" checked={inativos} onChange={(e) => setInativos(e.target.checked)} />
          Mostrar desativados
        </label>
      </div>
      {materiais.isLoading && <Carregando />}
      {materiais.error && <ErroCarga erro={materiais.error} />}
      {materiais.data && lista.length === 0 && (
        <Cartao>
          <Vazio>Nenhum material. Cadastre os que a clínica usa e o estoque mínimo de cada um.</Vazio>
        </Cartao>
      )}
      {lista.length > 0 && (
        <Cartao>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="text-left text-xs text-texto-suave">
                <tr>
                  <th className="py-1 pr-3 font-medium">Material</th>
                  <th className="py-1 pr-3 font-medium">Categoria</th>
                  <th className="py-1 pr-3 text-right font-medium">Custo médio</th>
                  <th className="py-1 pr-3 text-right font-medium">Mínimo</th>
                  <th className="py-1" />
                </tr>
              </thead>
              <tbody>
                {lista.map((m) => (
                  <tr key={m.id} className={`border-t border-borda ${m.active ? "" : "opacity-60"}`}>
                    <td className="py-2 pr-3 font-medium">
                      {m.name} <span className="text-xs font-normal text-texto-suave">({m.unit})</span>
                      {!m.active && <Etiqueta tom="alerta">desativado</Etiqueta>}
                    </td>
                    <td className="py-2 pr-3">{m.category ?? "—"}</td>
                    <td className="py-2 pr-3 text-right">{dinheiro(m.unit_cost)}</td>
                    <td className="py-2 pr-3 text-right">{qtd(m.min_quantity)}</td>
                    <td className="py-1 text-right">
                      <Botao variante="fantasma" className="min-h-9 px-2" onClick={() => setEditando(m)}>
                        Editar
                      </Botao>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Cartao>
      )}
      {editando && <FormMaterial material={editando === "novo" ? null : editando} aoFechar={() => setEditando(null)} />}
    </div>
  );
}

function FormMaterial({ material, aoFechar }: { material: Material | null; aoFechar: () => void }) {
  const cliente = useQueryClient();
  const [nome, setNome] = useState(material?.name ?? "");
  const [unidade, setUnidade] = useState(material?.unit ?? "un");
  const [categoria, setCategoria] = useState(material?.category ?? "");
  const [custo, setCusto] = useState(material ? String(Number(material.unit_cost)) : "");
  const [minimo, setMinimo] = useState(material?.min_quantity != null ? String(Number(material.min_quantity)) : "");
  const salvar = useMutation({
    mutationFn: async (ativo?: boolean) => {
      const corpo = {
        name: nome.trim(),
        unit: unidade.trim(),
        category: categoria.trim() || null,
        unit_cost: decimal(custo),
        min_quantity: minimo.trim() ? decimal(minimo) : null,
      };
      if (!material) return ok(await api.POST("/estoque/materiais", { body: corpo }));
      return ok(
        await api.PATCH("/estoque/materiais/{material_id}", {
          params: { path: { material_id: material.id } },
          body: ativo === undefined ? corpo : { active: ativo },
        }),
      );
    },
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["estoque"] });
      cliente.invalidateQueries({ queryKey: ["precificacao"] });
      aoFechar();
    },
  });
  return (
    <Modal titulo={material ? "Editar material" : "Novo material"} aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        <Campo rotulo="Nome" value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Resina A2" />
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo="Unidade de uso" value={unidade} onChange={(e) => setUnidade(e.target.value)} dica="un, ml, g, tubo, par…" />
          <Campo rotulo="Categoria" value={categoria} onChange={(e) => setCategoria(e.target.value)} placeholder="Restauração" />
          <Campo
            rotulo="Custo por unidade (R$)"
            inputMode="decimal"
            value={custo}
            onChange={(e) => setCusto(e.target.value)}
            dica={material ? "A próxima entrada com custo recalcula a média." : undefined}
          />
          <Campo rotulo="Estoque mínimo" inputMode="decimal" value={minimo} onChange={(e) => setMinimo(e.target.value)} dica="Abaixo disso aparece alerta." />
        </div>
        <div className="flex flex-wrap justify-between gap-2">
          {material ? (
            <Botao variante={material.active ? "perigo" : "secundario"} onClick={() => salvar.mutate(!material.active)} carregando={salvar.isPending}>
              {material.active ? "Desativar" : "Reativar"}
            </Botao>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Botao variante="secundario" onClick={aoFechar}>
              Cancelar
            </Botao>
            <Botao onClick={() => salvar.mutate(undefined)} carregando={salvar.isPending} disabled={!nome.trim() || !unidade.trim() || !custo.trim()}>
              Salvar
            </Botao>
          </div>
        </div>
      </div>
    </Modal>
  );
}

// ---------- movimentos ----------

const TIPO_MOV: Record<string, string> = {
  entrada: "Entrada",
  consumo: "Uso em paciente",
  saida: "Saída",
  ajuste: "Inventário",
};

function Movimentos() {
  const [material, setMaterial] = useState("");
  const materiais = useMateriais(true);
  const equipe = useEquipe();
  const movimentos = useQuery({
    queryKey: ["estoque", "movimentos", material],
    queryFn: async () =>
      ok(await api.GET("/estoque/movimentos", { params: { query: { material_id: material || undefined, limit: 200 } } })),
  });
  const nomeMaterial = (id: string) => materiais.data?.find((m) => m.id === id);
  return (
    <div className="flex flex-col gap-4">
      <Selecao rotulo="Material" value={material} onChange={(e) => setMaterial(e.target.value)} className="max-w-sm">
        <option value="">Todos (últimos 200)</option>
        {materiais.data?.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
          </option>
        ))}
      </Selecao>
      {movimentos.isLoading && <Carregando />}
      {movimentos.error && <ErroCarga erro={movimentos.error} />}
      {movimentos.data && movimentos.data.length === 0 && (
        <Cartao>
          <Vazio>Nenhum movimento.</Vazio>
        </Cartao>
      )}
      {movimentos.data && movimentos.data.length > 0 && (
        <Cartao>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-sm">
              <thead className="text-left text-xs text-texto-suave">
                <tr>
                  <th className="py-1 pr-3 font-medium">Quando</th>
                  <th className="py-1 pr-3 font-medium">Material</th>
                  <th className="py-1 pr-3 font-medium">Tipo</th>
                  <th className="py-1 pr-3 text-right font-medium">Qtd.</th>
                  <th className="py-1 pr-3 font-medium">Motivo</th>
                  <th className="py-1 font-medium">Por</th>
                </tr>
              </thead>
              <tbody>
                {movimentos.data.map((m) => {
                  const mat = nomeMaterial(m.material_id);
                  const n = Number(m.quantity);
                  return (
                    <tr key={m.id} className="border-t border-borda">
                      <td className="py-2 pr-3 whitespace-nowrap">{dataHoraBR(m.created_at)}</td>
                      <td className="py-2 pr-3">{mat?.name ?? "—"}</td>
                      <td className="py-2 pr-3">{TIPO_MOV[m.kind] ?? m.kind}</td>
                      <td className={`py-2 pr-3 text-right font-semibold ${n < 0 ? "text-perigo" : "text-sucesso"}`}>
                        {n > 0 ? "+" : ""}
                        {qtd(n)} {mat?.unit}
                      </td>
                      <td className="py-2 pr-3">{m.reason ?? (m.kind === "consumo" ? "Procedimento realizado" : "—")}</td>
                      <td className="py-2">{nomeMembro(equipe.data, m.recorded_by)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Cartao>
      )}
    </div>
  );
}
