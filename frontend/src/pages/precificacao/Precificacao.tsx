import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok } from "../../api/client";
import Modal from "../../components/Modal";
import { Abas, Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Selecao, Titulo, Vazio } from "../../components/ui";
import { dataBR } from "../../lib/datas";
import { nomeMembro, useDentistas } from "../../lib/equipe";
import Atribuicoes from "./Atribuicoes";
import Simular from "./Simular";
import Tabela from "./Tabela";

type Aba = "tabelas" | "atribuicoes" | "simular";

export default function Precificacao() {
  const [aba, setAba] = useState<Aba>("tabelas");
  const [aberta, setAberta] = useState<string | null>(null);
  return (
    <div>
      <Titulo>Precificação</Titulo>
      <Abas
        abas={[
          { id: "tabelas", rotulo: "Tabelas de preço" },
          { id: "atribuicoes", rotulo: "Quem usa cada tabela" },
          { id: "simular", rotulo: "Simular preço" },
        ]}
        atual={aba}
        aoMudar={(a) => {
          setAba(a);
          setAberta(null);
        }}
      />
      {aba === "tabelas" && (aberta ? <Tabela tabelaId={aberta} aoVoltar={() => setAberta(null)} /> : <ListaTabelas aoAbrir={setAberta} />)}
      {aba === "atribuicoes" && <Atribuicoes />}
      {aba === "simular" && <Simular />}
    </div>
  );
}

function ListaTabelas({ aoAbrir }: { aoAbrir: (id: string) => void }) {
  const [nova, setNova] = useState(false);
  const tabelas = useQuery({
    queryKey: ["precificacao", "tabelas"],
    queryFn: async () => ok(await api.GET("/precificacao/tabelas")),
  });
  const dentistas = useDentistas();
  return (
    <div className="flex flex-col gap-4">
      <Botao className="self-start" onClick={() => setNova(true)}>
        + Nova tabela
      </Botao>
      {tabelas.isLoading && <Carregando />}
      {tabelas.error && <ErroCarga erro={tabelas.error} />}
      {tabelas.data && tabelas.data.length === 0 && (
        <Cartao>
          <Vazio>Nenhuma tabela. Crie uma e importe a planilha de preços.</Vazio>
        </Cartao>
      )}
      <ul className="flex flex-col gap-2">
        {tabelas.data?.map((t) => (
          <li key={t.id}>
            <button
              type="button"
              onClick={() => aoAbrir(t.id)}
              className="flex min-h-14 w-full flex-wrap items-center gap-3 rounded-xl border border-borda bg-painel p-3 text-left hover:border-marca"
            >
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{t.name}</p>
                <p className="text-xs text-texto-suave">
                  {t.kind === "calculada" ? "Calculada por fórmula" : "Preço fixo"}
                  {t.parent_table_id && ` · herda de ${tabelas.data?.find((x) => x.id === t.parent_table_id)?.name ?? "outra"}`}
                  {t.calc_dentist_id && ` · parâmetros de ${nomeMembro(dentistas.data, t.calc_dentist_id)}`}
                  {` · criada em ${dataBR(t.created_at)}`}
                </p>
              </div>
              <Etiqueta tom={t.status === "ativa" ? "sucesso" : "alerta"}>{t.status}</Etiqueta>
            </button>
          </li>
        ))}
      </ul>
      {nova && <NovaTabela tabelas={tabelas.data ?? []} aoFechar={() => setNova(false)} aoCriar={aoAbrir} />}
    </div>
  );
}

function NovaTabela({
  tabelas,
  aoFechar,
  aoCriar,
}: {
  tabelas: { id: string; name: string; status: string }[];
  aoFechar: () => void;
  aoCriar: (id: string) => void;
}) {
  const cliente = useQueryClient();
  const [nome, setNome] = useState("");
  const [tipo, setTipo] = useState<"fixa" | "calculada">("fixa");
  const [pai, setPai] = useState("");
  const [ajuste, setAjuste] = useState("");
  const criar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/precificacao/tabelas", {
          body: {
            name: nome,
            kind: tipo,
            parent_table_id: tipo === "fixa" && pai ? pai : null,
            adjustment_pct: tipo === "fixa" && pai && ajuste ? ajuste.replace(",", ".") : null,
          },
        }),
      ),
    onSuccess: (t) => {
      cliente.invalidateQueries({ queryKey: ["precificacao"] });
      aoFechar();
      aoCriar(t.id);
    },
  });
  return (
    <Modal titulo="Nova tabela de preço" aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {criar.error && <Aviso tom="perigo">{criar.error.message}</Aviso>}
        <Campo rotulo="Nome" value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Tabela padrão 2027" />
        <Selecao rotulo="Tipo" value={tipo} onChange={(e) => setTipo(e.target.value as "fixa" | "calculada")}>
          <option value="fixa">Preço fixo (digitado ou importado)</option>
          <option value="calculada">Calculada por fórmula (custo + margem)</option>
        </Selecao>
        {tipo === "fixa" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Selecao rotulo="Herdar de (opcional)" value={pai} onChange={(e) => setPai(e.target.value)}>
              <option value="">— nenhuma —</option>
              {tabelas
                .filter((t) => t.status === "ativa")
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
            </Selecao>
            {pai && <Campo rotulo="Ajuste sobre a mãe (%)" placeholder="15 = +15%" value={ajuste} onChange={(e) => setAjuste(e.target.value)} />}
          </div>
        )}
        <p className="text-xs text-texto-suave">A tabela nasce com a versão 1 em rascunho. Nada vale até publicar.</p>
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao onClick={() => criar.mutate()} carregando={criar.isPending} disabled={!nome.trim()}>
            Criar
          </Botao>
        </div>
      </div>
    </Modal>
  );
}

