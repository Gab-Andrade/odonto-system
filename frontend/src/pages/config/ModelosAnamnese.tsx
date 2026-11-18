import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok } from "../../api/client";
import Modal from "../../components/Modal";
import { AreaTexto, Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Selecao, Vazio } from "../../components/ui";
import { dataBR } from "../../lib/datas";
import { CampoPergunta, type Pergunta } from "../prontuario/Anamnese";

/**
 * Modelos de anamnese: cada modelo tem versões. Edita-se sempre um rascunho; ao publicar,
 * ele passa a valer para as próximas respostas e a versão anterior fica guardada (as
 * respostas antigas continuam ligadas à versão que o paciente respondeu).
 */

const TIPOS: Record<Pergunta["type"], string> = {
  sim_nao: "Sim ou não",
  texto: "Texto livre",
  escolha_unica: "Uma opção da lista",
  multipla: "Várias opções da lista",
  numero: "Número",
  data: "Data",
};
const ESCOLHA = new Set<Pergunta["type"]>(["escolha_unica", "multipla"]);

export default function ModelosAnamnese() {
  const [aberto, setAberto] = useState<string | null>(null);
  return aberto ? <Modelo id={aberto} aoVoltar={() => setAberto(null)} /> : <ListaModelos aoAbrir={setAberto} />;
}

function ListaModelos({ aoAbrir }: { aoAbrir: (id: string) => void }) {
  const [inativos, setInativos] = useState(false);
  const [novo, setNovo] = useState(false);
  const modelos = useQuery({
    queryKey: ["anamnese", "modelos", inativos],
    queryFn: async () => ok(await api.GET("/prontuario/anamnese/modelos", { params: { query: { incluir_inativos: inativos } } })),
  });
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Botao onClick={() => setNovo(true)}>+ Novo modelo</Botao>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" className="size-5 accent-marca" checked={inativos} onChange={(e) => setInativos(e.target.checked)} />
          Mostrar desativados
        </label>
      </div>
      {modelos.isLoading && <Carregando />}
      {modelos.error && <ErroCarga erro={modelos.error} />}
      {modelos.data?.length === 0 && (
        <Cartao>
          <Vazio>Nenhum modelo de anamnese.</Vazio>
        </Cartao>
      )}
      <ul className="flex flex-col gap-2">
        {modelos.data?.map((m) => (
          <li key={m.id}>
            <button
              type="button"
              onClick={() => aoAbrir(m.id)}
              className={`flex min-h-14 w-full flex-wrap items-center gap-3 rounded-xl border border-borda bg-painel p-3 text-left hover:border-marca ${m.active ? "" : "opacity-60"}`}
            >
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{m.name}</p>
                <p className="text-xs text-texto-suave">
                  {m.published ? `Versão ${m.published.number} publicada em ${dataBR(m.published.published_at)}` : "Ainda não publicado"}
                  {m.description && ` · ${m.description}`}
                </p>
              </div>
              {m.draft && <Etiqueta tom="alerta">rascunho v{m.draft.number}</Etiqueta>}
              {!m.active && <Etiqueta tom="perigo">desativado</Etiqueta>}
            </button>
          </li>
        ))}
      </ul>
      {novo && <NovoModelo aoFechar={() => setNovo(false)} aoCriar={aoAbrir} />}
    </div>
  );
}

function NovoModelo({ aoFechar, aoCriar }: { aoFechar: () => void; aoCriar: (id: string) => void }) {
  const cliente = useQueryClient();
  const [nome, setNome] = useState("");
  const [descricao, setDescricao] = useState("");
  const criar = useMutation({
    mutationFn: async () =>
      ok(await api.POST("/prontuario/anamnese/modelos", { body: { name: nome.trim(), description: descricao.trim() || null, questions: [] } })),
    onSuccess: (m) => {
      cliente.invalidateQueries({ queryKey: ["anamnese"] });
      aoFechar();
      aoCriar(m.id);
    },
  });
  return (
    <Modal titulo="Novo modelo de anamnese" aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {criar.error && <Aviso tom="perigo">{criar.error.message}</Aviso>}
        <Campo rotulo="Nome" value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Anamnese infantil" />
        <Campo rotulo="Descrição (opcional)" value={descricao} onChange={(e) => setDescricao(e.target.value)} />
        <p className="text-xs text-texto-suave">O modelo nasce com um rascunho vazio. Ele só aparece para os pacientes depois de publicado.</p>
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

function Modelo({ id, aoVoltar }: { id: string; aoVoltar: () => void }) {
  const cliente = useQueryClient();
  const modelo = useQuery({
    queryKey: ["anamnese", "modelo", id],
    queryFn: async () => ok(await api.GET("/prontuario/anamnese/modelos/{template_id}", { params: { path: { template_id: id } } })),
  });
  const alterar = useMutation({
    mutationFn: async (corpo: { active?: boolean; name?: string; description?: string | null }) =>
      ok(await api.PATCH("/prontuario/anamnese/modelos/{template_id}", { params: { path: { template_id: id } }, body: corpo })),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["anamnese"] }),
  });
  const rascunho = useMutation({
    mutationFn: async () =>
      ok(await api.POST("/prontuario/anamnese/modelos/{template_id}/rascunho", { params: { path: { template_id: id } } })),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["anamnese"] }),
  });
  const [renomear, setRenomear] = useState(false);
  const m = modelo.data;
  // Edita o rascunho; sem rascunho, mostra a publicada (só leitura).
  const versaoId = m?.draft?.id ?? m?.published?.id;

  return (
    <div className="flex flex-col gap-4">
      <Botao variante="fantasma" className="self-start" onClick={aoVoltar}>
        ← Modelos
      </Botao>
      {modelo.isLoading && <Carregando />}
      {modelo.error && <ErroCarga erro={modelo.error} />}
      {m && (
        <>
          <Cartao
            titulo={
              <span className="flex flex-wrap items-center gap-2">
                {m.name}
                {!m.active && <Etiqueta tom="perigo">desativado</Etiqueta>}
              </span>
            }
            acoes={
              <>
                <Botao variante="secundario" onClick={() => setRenomear(true)}>
                  Renomear
                </Botao>
                <Botao variante={m.active ? "perigo" : "secundario"} carregando={alterar.isPending} onClick={() => alterar.mutate({ active: !m.active })}>
                  {m.active ? "Desativar" : "Reativar"}
                </Botao>
              </>
            }
          >
            {m.description && <p className="mb-2 text-sm">{m.description}</p>}
            {alterar.error && <Aviso tom="perigo">{alterar.error.message}</Aviso>}
            <p className="text-xs text-texto-suave">
              Versões:{" "}
              {[...m.versions]
                .sort((a, b) => b.number - a.number)
                .map((v) => `v${v.number} ${v.status === "publicada" ? "(publicada)" : v.status === "rascunho" ? "(rascunho)" : "(antiga)"}`)
                .join(" · ")}
            </p>
          </Cartao>
          {!m.draft && m.published && (
            <Aviso>
              Esta é a versão publicada (v{m.published.number}) e não muda mais.{" "}
              <button type="button" className="font-semibold underline" onClick={() => rascunho.mutate()} disabled={rascunho.isPending}>
                Criar rascunho para editar
              </button>
              {rascunho.error && <span className="block text-perigo">{rascunho.error.message}</span>}
            </Aviso>
          )}
          {versaoId && <Versao key={versaoId} id={versaoId} editavel={!!m.draft} temPublicada={!!m.published} />}
          {renomear && (
            <Renomear
              nome={m.name}
              descricao={m.description ?? ""}
              aoFechar={() => setRenomear(false)}
              aoSalvar={(name, description) => alterar.mutate({ name, description: description || null }, { onSuccess: () => setRenomear(false) })}
              salvando={alterar.isPending}
            />
          )}
        </>
      )}
    </div>
  );
}

function Renomear({
  nome,
  descricao,
  aoFechar,
  aoSalvar,
  salvando,
}: {
  nome: string;
  descricao: string;
  aoFechar: () => void;
  aoSalvar: (nome: string, descricao: string) => void;
  salvando: boolean;
}) {
  const [n, setN] = useState(nome);
  const [d, setD] = useState(descricao);
  return (
    <Modal titulo="Renomear modelo" aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        <Campo rotulo="Nome" value={n} onChange={(e) => setN(e.target.value)} />
        <Campo rotulo="Descrição" value={d} onChange={(e) => setD(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao onClick={() => aoSalvar(n.trim(), d.trim())} carregando={salvando} disabled={!n.trim()}>
            Salvar
          </Botao>
        </div>
      </div>
    </Modal>
  );
}

// ---------- edição das perguntas ----------

/** Pergunta em edição: `chave` só serve de key no React; opções como texto, uma por linha. */
interface Editavel extends Pergunta {
  chave: number;
  opcoesTexto: string;
}

let proximaChave = 1;

function editavel(p: Pergunta): Editavel {
  return { ...p, chave: proximaChave++, opcoesTexto: (p.options ?? []).join("\n") };
}

/** Identificador estável da pergunta a partir do texto (só para perguntas novas). */
function slug(texto: string, usados: Set<string>): string {
  const base =
    texto
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 34) || "pergunta";
  let id = base;
  for (let n = 2; usados.has(id); n++) id = `${base}_${n}`;
  return id;
}

function opcoes(p: Editavel): string[] {
  return [...new Set(p.opcoesTexto.split("\n").map((o) => o.trim()).filter(Boolean))];
}

/** Converte para o formato da API, gerando id para as perguntas novas. */
function paraApi(lista: Editavel[]): (Pergunta & { required: boolean; alert: boolean })[] {
  const usados = new Set(lista.map((p) => p.id).filter(Boolean));
  return lista.map((p) => {
    const id = p.id || slug(p.text, usados);
    usados.add(id);
    const escolha = ESCOLHA.has(p.type);
    const ops = escolha ? opcoes(p) : undefined;
    const alertas = escolha && p.alert ? (p.alert_options ?? []).filter((o) => ops?.includes(o)) : [];
    return {
      id,
      text: p.text.trim(),
      type: p.type,
      section: p.section?.trim() || undefined,
      help: p.help?.trim() || undefined,
      required: !!p.required,
      alert: !!p.alert,
      options: ops,
      alert_options: alertas.length ? alertas : undefined,
    };
  });
}

function Versao({ id, editavel: podeEditar, temPublicada }: { id: string; editavel: boolean; temPublicada: boolean }) {
  const versao = useQuery({
    queryKey: ["anamnese", "versao", id],
    queryFn: async () => ok(await api.GET("/prontuario/anamnese/versoes/{version_id}", { params: { path: { version_id: id } } })),
  });
  if (versao.isLoading) return <Carregando />;
  if (versao.error) return <ErroCarga erro={versao.error} />;
  if (!versao.data) return null;
  const perguntas = versao.data.questions as unknown as Pergunta[];
  return podeEditar ? (
    <Editor versaoId={id} numero={versao.data.number} inicial={perguntas} temPublicada={temPublicada} />
  ) : (
    <Previa perguntas={perguntas} />
  );
}

function Previa({ perguntas }: { perguntas: Pergunta[] }) {
  const [valores, setValores] = useState<Record<string, unknown>>({});
  // Título da seção só na primeira pergunta de cada seção.
  const titulos = perguntas.map((p, i) => {
    const anterior = perguntas.slice(0, i).findLast((x) => x.section)?.section;
    return p.section && p.section !== anterior ? p.section : null;
  });
  return (
    <Cartao titulo="Como o formulário aparece">
      {perguntas.length === 0 && <Vazio>Sem perguntas.</Vazio>}
      <div className="flex flex-col gap-4">
        {perguntas.map((p, i) => {
          const titulo = titulos[i];
          return (
            <div key={p.id} className="flex flex-col gap-2">
              {titulo && <h3 className="border-b border-borda pb-1 text-sm font-bold text-marca">{titulo}</h3>}
              <CampoPergunta pergunta={p} valor={valores[p.id]} aoMudar={(v) => setValores((x) => ({ ...x, [p.id]: v }))} />
            </div>
          );
        })}
      </div>
    </Cartao>
  );
}

function Editor({ versaoId, numero, inicial, temPublicada }: { versaoId: string; numero: number; inicial: Pergunta[]; temPublicada: boolean }) {
  const cliente = useQueryClient();
  const [lista, setLista] = useState<Editavel[]>(() => inicial.map(editavel));
  const [alterado, setAlterado] = useState(false);
  const [ver, setVer] = useState(false);
  const mudar = (fn: (l: Editavel[]) => Editavel[]) => {
    setLista(fn);
    setAlterado(true);
  };
  const atualizar = (chave: number, campos: Partial<Editavel>) => mudar((l) => l.map((p) => (p.chave === chave ? { ...p, ...campos } : p)));
  const mover = (i: number, d: number) =>
    mudar((l) => {
      const n = [...l];
      [n[i], n[i + d]] = [n[i + d], n[i]];
      return n;
    });
  const nova = () =>
    mudar((l) => [...l, editavel({ id: "", text: "", type: "sim_nao", section: l.at(-1)?.section, required: false, alert: false })]);

  const invalida = lista.find((p) => !p.text.trim() || (ESCOLHA.has(p.type) && opcoes(p).length < 2));
  const salvar = useMutation({
    mutationFn: async () =>
      ok(await api.PUT("/prontuario/anamnese/versoes/{version_id}", { params: { path: { version_id: versaoId } }, body: { questions: paraApi(lista) } })),
    onSuccess: (v) => {
      setLista((v.questions as unknown as Pergunta[]).map(editavel));
      setAlterado(false);
      cliente.invalidateQueries({ queryKey: ["anamnese", "versao", versaoId] });
    },
  });
  const publicar = useMutation({
    mutationFn: async () => {
      if (alterado) await salvar.mutateAsync();
      return ok(await api.POST("/prontuario/anamnese/versoes/{version_id}/publicar", { params: { path: { version_id: versaoId } } }));
    },
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["anamnese"] }),
  });
  const descartar = useMutation({
    mutationFn: async () => ok(await api.DELETE("/prontuario/anamnese/versoes/{version_id}", { params: { path: { version_id: versaoId } } })),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["anamnese"] }),
  });
  const erro = salvar.error ?? publicar.error ?? descartar.error;

  return (
    <div className="flex flex-col gap-3">
      <div className="sticky top-14 z-[5] flex flex-wrap items-center gap-2 rounded-xl border border-borda bg-painel/95 p-3 backdrop-blur lg:top-0">
        <p className="mr-auto text-sm">
          <strong>Rascunho v{numero}</strong> · {lista.length} pergunta{lista.length === 1 ? "" : "s"}
          {alterado && <span className="text-alerta"> · alterações não salvas</span>}
        </p>
        <Botao variante="secundario" onClick={() => setVer((v) => !v)}>
          {ver ? "Editar" : "Ver como fica"}
        </Botao>
        {temPublicada && (
          <Botao variante="fantasma" onClick={() => confirm("Descartar o rascunho e voltar para a versão publicada?") && descartar.mutate()} carregando={descartar.isPending}>
            Descartar
          </Botao>
        )}
        <Botao variante="secundario" onClick={() => salvar.mutate()} carregando={salvar.isPending} disabled={!alterado || !!invalida}>
          Salvar rascunho
        </Botao>
        <Botao onClick={() => publicar.mutate()} carregando={publicar.isPending} disabled={!lista.length || !!invalida}>
          Publicar
        </Botao>
      </div>
      {erro && <Aviso tom="perigo">{erro.message}</Aviso>}
      {invalida && <Aviso tom="alerta">Cada pergunta precisa de texto, e as de lista, de pelo menos duas opções.</Aviso>}
      {ver ? (
        <Previa perguntas={paraApi(lista)} />
      ) : (
        <>
          {lista.length === 0 && (
            <Cartao>
              <Vazio>Nenhuma pergunta. Comece adicionando uma.</Vazio>
            </Cartao>
          )}
          {lista.map((p, i) => (
            <EditorPergunta
              key={p.chave}
              pergunta={p}
              primeira={i === 0}
              ultima={i === lista.length - 1}
              aoMudar={(campos) => atualizar(p.chave, campos)}
              aoMover={(d) => mover(i, d)}
              aoRemover={() => mudar((l) => l.filter((x) => x.chave !== p.chave))}
            />
          ))}
          <Botao variante="secundario" className="self-start" onClick={nova}>
            + Adicionar pergunta
          </Botao>
        </>
      )}
      <p className="text-xs text-texto-suave">
        Publicar faz esta versão valer para as próximas anamneses. As já respondidas continuam com as perguntas da época.
      </p>
    </div>
  );
}

function EditorPergunta({
  pergunta: p,
  primeira,
  ultima,
  aoMudar,
  aoMover,
  aoRemover,
}: {
  pergunta: Editavel;
  primeira: boolean;
  ultima: boolean;
  aoMudar: (campos: Partial<Editavel>) => void;
  aoMover: (d: number) => void;
  aoRemover: () => void;
}) {
  const escolha = ESCOLHA.has(p.type);
  const ops = escolha ? opcoes(p) : [];
  const alertas = p.alert_options ?? [];
  return (
    <section className="flex flex-col gap-3 rounded-xl border border-borda bg-painel p-4">
      <div className="flex flex-wrap items-end gap-3">
        <Campo rotulo="Pergunta" value={p.text} onChange={(e) => aoMudar({ text: e.target.value })} className="min-w-60 flex-[3]" />
        <Selecao rotulo="Tipo de resposta" value={p.type} onChange={(e) => aoMudar({ type: e.target.value as Pergunta["type"] })} className="min-w-44 flex-1">
          {Object.entries(TIPOS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Selecao>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Campo rotulo="Seção (opcional)" value={p.section ?? ""} onChange={(e) => aoMudar({ section: e.target.value })} placeholder="Saúde geral" />
        <Campo rotulo="Dica (opcional)" value={p.help ?? ""} onChange={(e) => aoMudar({ help: e.target.value })} />
      </div>
      {escolha && (
        <AreaTexto
          rotulo="Opções (uma por linha)"
          value={p.opcoesTexto}
          onChange={(e) => aoMudar({ opcoesTexto: e.target.value })}
          placeholder={"Nunca\nÀs vezes\nSempre"}
        />
      )}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
        <label className="flex min-h-10 items-center gap-2">
          <input type="checkbox" className="size-5 accent-marca" checked={!!p.required} onChange={(e) => aoMudar({ required: e.target.checked })} />
          Obrigatória
        </label>
        <label className="flex min-h-10 items-center gap-2" title="A resposta aparece em destaque no cabeçalho do paciente">
          <input type="checkbox" className="size-5 accent-marca" checked={!!p.alert} onChange={(e) => aoMudar({ alert: e.target.checked })} />
          Gera alerta
        </label>
        <span className="ml-auto flex gap-1">
          <Botao variante="fantasma" className="min-h-9 px-2" disabled={primeira} onClick={() => aoMover(-1)} aria-label="Subir">
            ↑
          </Botao>
          <Botao variante="fantasma" className="min-h-9 px-2" disabled={ultima} onClick={() => aoMover(1)} aria-label="Descer">
            ↓
          </Botao>
          <Botao variante="fantasma" className="min-h-9 px-2 text-perigo" onClick={aoRemover}>
            Remover
          </Botao>
        </span>
      </div>
      {escolha && p.alert && ops.length > 0 && (
        <div className="flex flex-col gap-1 text-sm">
          <span className="text-texto-suave">Alerta só nestas opções (nenhuma marcada = qualquer resposta):</span>
          <div className="flex flex-wrap gap-3">
            {ops.map((o) => (
              <label key={o} className="flex min-h-10 items-center gap-2">
                <input
                  type="checkbox"
                  className="size-5 accent-marca"
                  checked={alertas.includes(o)}
                  onChange={(e) => aoMudar({ alert_options: e.target.checked ? [...alertas, o] : alertas.filter((x) => x !== o) })}
                />
                {o}
              </label>
            ))}
          </div>
        </div>
      )}
      {p.id && <p className="text-xs text-texto-suave">Identificador: {p.id}</p>}
    </section>
  );
}
