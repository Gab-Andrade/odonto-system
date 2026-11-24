import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import { NOME_PAPEL, useSessao, type Papel } from "../../auth/sessao";
import Modal from "../../components/Modal";
import { Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Selecao, Vazio } from "../../components/ui";
import { dataBR, dataHoraBR } from "../../lib/datas";

/**
 * Cadastro de equipe (só administrador). A API é quem garante as regras; a tela só evita
 * oferecer o que vai ser recusado:
 * - e-mail novo recebe senha provisória (a pessoa define a dela no primeiro acesso);
 * - e-mail que já tem cadastro recebe convite com código, entregue pessoalmente;
 * - outro administrador só é rebaixado ou desativado se ele mesmo aceitar o pedido;
 * - nome, CRO e senha de quem também atua em outra clínica não mudam por aqui;
 * - a senha de outro administrador não é redefinida.
 */

type Membro = Schemas["MemberOut"];
type Pedido = Schemas["AdminChangeOut"];
type Segredo = { tipo: "senha" | "codigo"; pessoa: string; valor: string };

const PAPEIS = Object.keys(NOME_PAPEL) as Papel[];

export default function Equipe() {
  const [inativos, setInativos] = useState(false);
  const [novo, setNovo] = useState(false);
  const [editando, setEditando] = useState<Membro | null>(null);
  const [segredo, setSegredo] = useState<Segredo | null>(null);

  const membros = useQuery({
    queryKey: ["equipe-admin", "membros", inativos],
    queryFn: async () =>
      ok(await api.GET("/equipe/membros", { params: { query: { incluir_inativos: inativos } } })),
  });

  return (
    <div className="flex flex-col gap-4">
      <Pedidos />
      <Convites aoGerar={setSegredo} />
      <div className="flex flex-wrap items-center gap-3">
        <Botao onClick={() => setNovo(true)}>+ Adicionar pessoa</Botao>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-5 accent-marca"
            checked={inativos}
            onChange={(e) => setInativos(e.target.checked)}
          />
          Mostrar desativados
        </label>
      </div>
      {membros.isLoading && <Carregando />}
      {membros.error && <ErroCarga erro={membros.error} />}
      {membros.data?.length === 0 && (
        <Cartao>
          <Vazio>Ninguém na equipe.</Vazio>
        </Cartao>
      )}
      <ul className="flex flex-col gap-2">
        {membros.data?.map((m) => (
          <li key={m.user_id}>
            <button
              type="button"
              onClick={() => setEditando(m)}
              className={`flex min-h-14 w-full flex-wrap items-center gap-3 rounded-xl border border-borda bg-painel p-3 text-left hover:border-marca ${m.active ? "" : "opacity-60"}`}
            >
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{m.full_name}</p>
                <p className="truncate text-xs text-texto-suave">
                  {m.email}
                  {m.cro && ` · CRO ${m.cro}`} · desde {dataBR(m.since)}
                </p>
              </div>
              <Etiqueta tom={m.role === "admin" ? "alerta" : "info"}>{NOME_PAPEL[m.role]}</Etiqueta>
              {m.other_clinics && <Etiqueta>também em outra clínica</Etiqueta>}
              {!m.active && <Etiqueta tom="perigo">desativado</Etiqueta>}
            </button>
          </li>
        ))}
      </ul>
      {novo && (
        <NovoMembro
          aoFechar={() => setNovo(false)}
          aoCriar={(s) => {
            setNovo(false);
            setSegredo(s);
          }}
        />
      )}
      {editando && (
        <EditarMembro
          membro={editando}
          aoFechar={() => setEditando(null)}
          aoRedefinir={(s) => {
            setSegredo({ tipo: "senha", pessoa: editando.full_name, valor: s });
            setEditando(null);
          }}
        />
      )}
      {segredo && <SegredoGerado {...segredo} aoFechar={() => setSegredo(null)} />}
    </div>
  );
}

function useAtualizarEquipe() {
  const cliente = useQueryClient();
  return () => {
    cliente.invalidateQueries({ queryKey: ["equipe-admin"] });
    cliente.invalidateQueries({ queryKey: ["equipe"] }); // lista usada na agenda, planos etc.
  };
}

function descricaoPedido(p: Pedido): string {
  return p.action === "rebaixar" && p.new_role
    ? `rebaixar ${p.target_name} para ${NOME_PAPEL[p.new_role]}`
    : `desativar o acesso de ${p.target_name}`;
}

function Convites({ aoGerar }: { aoGerar: (s: Segredo) => void }) {
  const atualizar = useAtualizarEquipe();
  const [erro, setErro] = useState<string | null>(null);
  const convites = useQuery({
    queryKey: ["equipe-admin", "convites"],
    queryFn: async () => ok(await api.GET("/equipe/convites")),
  });
  const renovar = useMutation({
    mutationFn: async (id: string) =>
      ok(await api.POST("/equipe/convites/{invite_id}/novo-codigo", { params: { path: { invite_id: id } } })),
    onSuccess: (r) => {
      atualizar();
      aoGerar({ tipo: "codigo", pessoa: r.email, valor: r.invite_code });
    },
    onError: (e) => setErro(e.message),
  });
  const cancelar = useMutation({
    mutationFn: async (id: string) =>
      ok(await api.DELETE("/equipe/convites/{invite_id}", { params: { path: { invite_id: id } } })),
    onSuccess: atualizar,
    onError: (e) => setErro(e.message),
  });

  if (!convites.data?.length) return null;
  const agora = convites.dataUpdatedAt; // hora da busca: o render fica puro
  return (
    <Cartao titulo="Convites aguardando o código">
      <p className="mb-3 text-sm text-texto-suave">
        Estes e-mails já usam o sistema em outra clínica. O acesso a esta clínica só começa quando a pessoa digitar,
        na tela de entrada, o código que você entregou a ela.
      </p>
      {erro && <Aviso tom="perigo">{erro}</Aviso>}
      <ul className="flex flex-col gap-2">
        {convites.data.map((c) => {
          const vencido = new Date(c.expires_at).getTime() <= agora;
          return (
            <li key={c.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-borda p-3">
              <div className="min-w-0 flex-1 text-sm">
                <p className="font-semibold">{c.email}</p>
                <p className="text-xs text-texto-suave">
                  {NOME_PAPEL[c.role]} · {vencido ? "código vencido" : `código vale até ${dataHoraBR(c.expires_at)}`}
                </p>
              </div>
              {vencido && <Etiqueta tom="alerta">vencido</Etiqueta>}
              <Botao variante="secundario" carregando={renovar.isPending} onClick={() => renovar.mutate(c.id)}>
                Novo código
              </Botao>
              <Botao
                variante="fantasma"
                carregando={cancelar.isPending}
                onClick={() => {
                  if (window.confirm(`Cancelar o convite de ${c.email}?`)) cancelar.mutate(c.id);
                }}
              >
                Cancelar
              </Botao>
            </li>
          );
        })}
      </ul>
    </Cartao>
  );
}

function Pedidos() {
  const eu = useSessao((s) => s.usuario?.id);
  const atualizar = useAtualizarEquipe();
  const [erro, setErro] = useState<string | null>(null);
  const pedidos = useQuery({
    queryKey: ["equipe-admin", "pedidos"],
    queryFn: async () => ok(await api.GET("/equipe/solicitacoes")),
  });
  const decidir = useMutation({
    mutationFn: async ({ id, acao }: { id: string; acao: "aceitar" | "recusar" | "cancelar" }) => {
      const params = { params: { path: { request_id: id } } };
      if (acao === "aceitar") return ok(await api.POST("/equipe/solicitacoes/{request_id}/aceitar", params));
      if (acao === "recusar") return ok(await api.POST("/equipe/solicitacoes/{request_id}/recusar", params));
      return ok(await api.POST("/equipe/solicitacoes/{request_id}/cancelar", params));
    },
    onSuccess: () => {
      setErro(null);
      atualizar();
    },
    onError: (e) => setErro(e.message),
  });

  if (!pedidos.data?.length) return null;
  return (
    <Cartao titulo="Pedidos de mudança de administrador">
      {erro && <Aviso tom="perigo">{erro}</Aviso>}
      <ul className="flex flex-col gap-3">
        {pedidos.data.map((p) => {
          const meu = p.requested_by === eu;
          const paraMim = p.target_user_id === eu;
          return (
            <li key={p.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-borda p-3">
              <div className="min-w-0 flex-1 text-sm">
                <p>
                  <strong>{meu ? "Você" : p.requested_by_name}</strong> pediu para{" "}
                  {paraMim ? descricaoPedido(p).replace(p.target_name, "você") : descricaoPedido(p)}.
                </p>
                {p.reason && <p className="text-texto-suave">Motivo: {p.reason}</p>}
                <p className="text-xs text-texto-suave">
                  Pedido em {dataHoraBR(p.created_at)} · vale até {dataHoraBR(p.expires_at)}
                  {!paraMim && ` · só vale se ${p.target_name} aceitar`}
                </p>
              </div>
              {paraMim && (
                <div className="flex gap-2">
                  <Botao
                    variante="secundario"
                    carregando={decidir.isPending}
                    onClick={() => decidir.mutate({ id: p.id, acao: "recusar" })}
                  >
                    Recusar
                  </Botao>
                  <Botao
                    variante="perigo"
                    carregando={decidir.isPending}
                    onClick={() => {
                      if (window.confirm("Aceitar? Você perde o acesso de administrador na hora."))
                        decidir.mutate({ id: p.id, acao: "aceitar" });
                    }}
                  >
                    Aceitar
                  </Botao>
                </div>
              )}
              {meu && (
                <Botao
                  variante="secundario"
                  carregando={decidir.isPending}
                  onClick={() => decidir.mutate({ id: p.id, acao: "cancelar" })}
                >
                  Cancelar pedido
                </Botao>
              )}
            </li>
          );
        })}
      </ul>
    </Cartao>
  );
}

function NovoMembro({ aoFechar, aoCriar }: { aoFechar: () => void; aoCriar: (s: Segredo) => void }) {
  const atualizar = useAtualizarEquipe();
  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const [cro, setCro] = useState("");
  const [papel, setPapel] = useState<Papel>("dentista");
  const criar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/equipe/membros", {
          body: { email, full_name: nome, cro: cro.trim() || null, role: papel },
        }),
      ),
    onSuccess: (r) => {
      atualizar();
      if (r.invite && r.invite_code) aoCriar({ tipo: "codigo", pessoa: r.invite.email, valor: r.invite_code });
      else if (r.member && r.temporary_password)
        aoCriar({ tipo: "senha", pessoa: r.member.full_name, valor: r.temporary_password });
      else aoFechar();
    },
  });

  return (
    <Modal titulo="Adicionar pessoa à equipe" aberto aoFechar={aoFechar}>
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          criar.mutate();
        }}
      >
        <Campo rotulo="E-mail" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" />
        <Campo rotulo="Nome completo" required maxLength={200} value={nome} onChange={(e) => setNome(e.target.value)} />
        <Selecao rotulo="Papel" value={papel} onChange={(e) => setPapel(e.target.value as Papel)}>
          {PAPEIS.map((p) => (
            <option key={p} value={p}>
              {NOME_PAPEL[p]}
            </option>
          ))}
        </Selecao>
        <Campo rotulo="CRO (dentistas)" maxLength={30} value={cro} onChange={(e) => setCro(e.target.value)} />
        <p className="text-xs text-texto-suave">
          O sistema gera uma senha provisória, mostrada uma única vez; no primeiro acesso a pessoa define a dela.
          Se o e-mail já usa o sistema em outra clínica, você recebe um código para entregar a ela: o acesso a esta
          clínica só começa quando ela digitar o código.
        </p>
        {criar.error && <Aviso tom="perigo">{criar.error.message}</Aviso>}
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" carregando={criar.isPending}>
            Adicionar
          </Botao>
        </div>
      </form>
    </Modal>
  );
}

function SegredoGerado({ tipo, pessoa, valor, aoFechar }: Segredo & { aoFechar: () => void }) {
  const [copiado, setCopiado] = useState(false);
  return (
    <Modal titulo={tipo === "senha" ? "Senha provisória" : "Código do convite"} aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-4">
        {tipo === "senha" ? (
          <p className="text-sm">
            Entregue esta senha a <strong>{pessoa}</strong>. No primeiro acesso, o sistema pede que ela defina uma
            senha própria. Ela aparece só agora; se perder, gere outra.
          </p>
        ) : (
          <p className="text-sm">
            <strong>{pessoa}</strong> já usa o sistema em outra clínica. Entregue este código pessoalmente: na tela de
            entrada, em “Recebi um código de uma clínica”, ela digita o código com o e-mail e a senha dela. Vale por
            7 dias e aparece só agora.
          </p>
        )}
        <p className="rounded-lg border border-borda bg-fundo p-4 text-center font-mono text-2xl tracking-wider select-all">
          {valor}
        </p>
        <div className="flex justify-end gap-2">
          <Botao
            variante="secundario"
            onClick={() => {
              navigator.clipboard
                ?.writeText(valor)
                .then(() => setCopiado(true))
                .catch(() => setCopiado(false));
            }}
          >
            {copiado ? "Copiada" : "Copiar"}
          </Botao>
          <Botao onClick={aoFechar}>Pronto</Botao>
        </div>
      </div>
    </Modal>
  );
}

function EditarMembro({
  membro: m,
  aoFechar,
  aoRedefinir,
}: {
  membro: Membro;
  aoFechar: () => void;
  aoRedefinir: (senha: string) => void;
}) {
  const eu = useSessao((s) => s.usuario?.id);
  const souEu = m.user_id === eu;
  const outroAdmin = m.role === "admin" && m.active && !souEu;
  // Nome e CRO de quem atua em outra clínica, ou de outro admin, só a própria pessoa muda.
  const dadosBloqueados = m.other_clinics || outroAdmin;
  const atualizar = useAtualizarEquipe();
  const [nome, setNome] = useState(m.full_name);
  const [cro, setCro] = useState(m.cro ?? "");
  const [papel, setPapel] = useState<Papel>(m.role);
  const [ativo, setAtivo] = useState(m.active);
  const [erro, setErro] = useState<string | null>(null);

  const salvar = useMutation({
    mutationFn: async () => {
      const body: Schemas["MemberUpdate"] = {};
      if (!dadosBloqueados && nome.trim() !== m.full_name) body.full_name = nome;
      if (!dadosBloqueados && (cro.trim() || null) !== m.cro) body.cro = cro.trim() || null;
      if (!outroAdmin && papel !== m.role) body.role = papel;
      if (!outroAdmin && ativo !== m.active) body.active = ativo;
      if (Object.keys(body).length === 0) return null;
      return ok(await api.PATCH("/equipe/membros/{user_id}", { params: { path: { user_id: m.user_id } }, body }));
    },
    onSuccess: () => {
      atualizar();
      aoFechar();
    },
    onError: (e) => setErro(e.message),
  });
  const redefinir = useMutation({
    mutationFn: async () =>
      ok(await api.POST("/equipe/membros/{user_id}/redefinir-senha", { params: { path: { user_id: m.user_id } } })),
    onSuccess: (r) => aoRedefinir(r.temporary_password),
    onError: (e) => setErro(e.message),
  });
  const podeRedefinir = !souEu && !m.other_clinics && m.role !== "admin";

  return (
    <Modal titulo={m.full_name} aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-texto-suave">{m.email}</p>
        {m.other_clinics && (
          <Aviso>Esta pessoa também atua em outra clínica: nome, CRO e senha são dela e não mudam por aqui.</Aviso>
        )}
        <Campo rotulo="Nome completo" maxLength={200} value={nome} disabled={dadosBloqueados} onChange={(e) => setNome(e.target.value)} />
        <Campo rotulo="CRO" maxLength={30} value={cro} disabled={dadosBloqueados} onChange={(e) => setCro(e.target.value)} />
        {outroAdmin ? (
          <PedidoAdmin membro={m} aoEnviar={aoFechar} />
        ) : (
          <>
            <Selecao rotulo="Papel" value={papel} onChange={(e) => setPapel(e.target.value as Papel)}>
              {PAPEIS.map((p) => (
                <option key={p} value={p}>
                  {NOME_PAPEL[p]}
                </option>
              ))}
            </Selecao>
            <label className="flex min-h-11 items-center gap-2 text-sm">
              <input type="checkbox" className="size-5 accent-marca" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} />
              Acesso ativo nesta clínica
            </label>
            {souEu && m.role === "admin" && (papel !== "admin" || !ativo) && (
              <Aviso tom="alerta">Você vai perder o acesso de administrador assim que salvar.</Aviso>
            )}
          </>
        )}
        {erro && <Aviso tom="perigo">{erro}</Aviso>}
        <div className="flex flex-wrap justify-between gap-2">
          {podeRedefinir ? (
            <Botao
              variante="secundario"
              carregando={redefinir.isPending}
              onClick={() => {
                if (window.confirm(`Gerar uma senha nova para ${m.full_name}? A atual deixa de valer.`)) redefinir.mutate();
              }}
            >
              Redefinir senha
            </Botao>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Botao variante="secundario" onClick={aoFechar}>
              Cancelar
            </Botao>
            <Botao carregando={salvar.isPending} onClick={() => salvar.mutate()}>
              Salvar
            </Botao>
          </div>
        </div>
      </div>
    </Modal>
  );
}

/** Outro administrador: rebaixar ou desativar vira pedido para um segundo admin confirmar. */
function PedidoAdmin({ membro: m, aoEnviar }: { membro: Membro; aoEnviar: () => void }) {
  const atualizar = useAtualizarEquipe();
  const [acao, setAcao] = useState<string>("");
  const [motivo, setMotivo] = useState("");
  const pedir = useMutation({
    mutationFn: async () => {
      const desativar = acao === "desativar";
      return ok(
        await api.POST("/equipe/solicitacoes", {
          body: {
            user_id: m.user_id,
            action: desativar ? "desativar" : "rebaixar",
            new_role: desativar ? null : (acao as Papel),
            reason: motivo.trim() || null,
          },
        }),
      );
    },
    onSuccess: () => {
      atualizar();
      aoEnviar();
    },
  });
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-borda p-3">
      <p className="text-sm">
        <strong>Administrador.</strong> Para rebaixar ou desativar, faça um pedido: ele só vale quando
        {m.full_name} aceitar (prazo de 7 dias).
      </p>
      <Selecao rotulo="Pedir para" value={acao} onChange={(e) => setAcao(e.target.value)}>
        <option value="">Escolha…</option>
        {PAPEIS.filter((p) => p !== "admin").map((p) => (
          <option key={p} value={p}>
            Rebaixar para {NOME_PAPEL[p]}
          </option>
        ))}
        <option value="desativar">Desativar o acesso</option>
      </Selecao>
      <Campo rotulo="Motivo (opcional)" maxLength={300} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
      {pedir.error && <Aviso tom="perigo">{pedir.error.message}</Aviso>}
      <Botao variante="secundario" disabled={!acao} carregando={pedir.isPending} onClick={() => pedir.mutate()}>
        Enviar pedido
      </Botao>
    </div>
  );
}
