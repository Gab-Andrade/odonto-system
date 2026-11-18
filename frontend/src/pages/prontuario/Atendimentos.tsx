import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import { DENTISTAS, temPapel, useSessao } from "../../auth/sessao";
import { AreaTexto, Aviso, Botao, Cartao, Carregando, ErroCarga, Etiqueta, Vazio } from "../../components/ui";
import { dataHoraBR } from "../../lib/datas";
import { nomeMembro, useEquipe } from "../../lib/equipe";

type Paciente = Schemas["PatientOut"];
type Nota = Schemas["NoteOut"];

/**
 * Atendimentos e evolução clínica. Evolução e adendo são imutáveis e só do dentista autor;
 * atendimento fechado só recebe adendo. O botão Imprimir gera o prontuário para assinatura
 * à mão (ICP-Brasil em stand-by).
 */
export default function Atendimentos({ paciente }: { paciente: Paciente }) {
  const { papel, usuario } = useSessao();
  const cliente = useQueryClient();
  const equipe = useEquipe();
  const clinico = temPapel(papel, ...DENTISTAS);
  const [erro, setErro] = useState<string | null>(null);

  const atendimentos = useQuery({
    queryKey: ["atendimentos", paciente.id],
    queryFn: async () =>
      ok(
        await api.GET("/prontuario/pacientes/{patient_id}/atendimentos", {
          params: { path: { patient_id: paciente.id } },
        }),
      ),
  });
  const notas = useQuery({
    queryKey: ["evolucoes", paciente.id],
    queryFn: async () =>
      ok(
        await api.GET("/prontuario/pacientes/{patient_id}/evolucoes", {
          params: { path: { patient_id: paciente.id } },
        }),
      ),
  });

  const atualizar = () => {
    cliente.invalidateQueries({ queryKey: ["atendimentos", paciente.id] });
    cliente.invalidateQueries({ queryKey: ["evolucoes", paciente.id] });
    setErro(null);
  };

  const abrir = useMutation({
    mutationFn: async () =>
      ok(await api.POST("/prontuario/atendimentos", { body: { patient_id: paciente.id } })),
    onSuccess: atualizar,
    onError: (e) => setErro(e.message),
  });

  const porAtendimento = new Map<string, Nota[]>();
  for (const n of notas.data ?? []) {
    porAtendimento.set(n.encounter_id, [...(porAtendimento.get(n.encounter_id) ?? []), n]);
  }
  const lista = [...(atendimentos.data ?? [])].sort((a, b) => b.started_at.localeCompare(a.started_at));
  const meuAberto = lista.some((a) => a.status === "aberto" && a.dentist_id === usuario?.id);

  return (
    <div className="flex flex-col gap-4">
      <div className="nao-imprimir flex flex-wrap gap-2">
        {clinico && !meuAberto && (
          <Botao onClick={() => abrir.mutate()} carregando={abrir.isPending}>
            + Abrir atendimento (encaixe)
          </Botao>
        )}
        <Botao variante="secundario" onClick={() => window.print()}>
          Imprimir prontuário
        </Botao>
      </div>
      <div className="hidden print:block">
        <h2 className="text-lg font-bold">Prontuário · {paciente.full_name}</h2>
        <p className="text-sm">Impresso em {dataHoraBR(new Date().toISOString())}</p>
      </div>
      {erro && <Aviso tom="perigo">{erro}</Aviso>}
      {(atendimentos.isLoading || notas.isLoading) && <Carregando />}
      {atendimentos.error && <ErroCarga erro={atendimentos.error} />}
      {atendimentos.data && lista.length === 0 && (
        <Cartao>
          <Vazio>Nenhum atendimento ainda. Inicie pela agenda ou abra um encaixe.</Vazio>
        </Cartao>
      )}
      {lista.map((a) => (
        <Atendimento
          key={a.id}
          atendimento={a}
          notas={porAtendimento.get(a.id) ?? []}
          dentista={nomeMembro(equipe.data, a.dentist_id)}
          autorNome={(id) => nomeMembro(equipe.data, id)}
          meu={a.dentist_id === usuario?.id}
          aoMudar={atualizar}
        />
      ))}
      <div className="hidden print:block print:pt-16">
        <p>______________________________________</p>
        <p className="text-sm">Assinatura e carimbo do(a) cirurgião(ã)-dentista</p>
      </div>
    </div>
  );
}

function Atendimento({
  atendimento: a,
  notas,
  dentista,
  autorNome,
  meu,
  aoMudar,
}: {
  atendimento: Schemas["EncounterSummary"];
  notas: Nota[];
  dentista: string;
  autorNome: (id: string) => string;
  meu: boolean;
  aoMudar: () => void;
}) {
  const [texto, setTexto] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const aberto = a.status === "aberto";
  const evolucoes = notas.filter((n) => n.kind === "evolucao");
  const adendos = (id: string) => notas.filter((n) => n.amends_id === id);

  const evoluir = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/prontuario/atendimentos/{encounter_id}/evolucoes", {
          params: { path: { encounter_id: a.id } },
          body: { content: texto },
        }),
      ),
    onSuccess: () => {
      setTexto("");
      aoMudar();
    },
    onError: (e) => setErro(e.message),
  });
  const fechar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/prontuario/atendimentos/{encounter_id}/fechar", {
          params: { path: { encounter_id: a.id } },
        }),
      ),
    onSuccess: aoMudar,
    onError: (e) => setErro(e.message),
  });

  return (
    <Cartao
      titulo={
        <span className="flex flex-wrap items-center gap-2">
          {dataHoraBR(a.started_at)} · {dentista}
          <Etiqueta tom={aberto ? "alerta" : "sucesso"}>{aberto ? "Aberto" : "Fechado"}</Etiqueta>
        </span>
      }
      acoes={
        aberto && meu ? (
          <Botao variante="secundario" className="nao-imprimir" onClick={() => fechar.mutate()} carregando={fechar.isPending}>
            Fechar atendimento
          </Botao>
        ) : undefined
      }
    >
      {erro && <Aviso tom="perigo">{erro}</Aviso>}
      {evolucoes.length === 0 && <p className="text-sm text-texto-suave">Sem evolução registrada.</p>}
      <ul className="flex flex-col gap-3">
        {evolucoes.map((n) => (
          <li key={n.id} className="rounded-lg border border-borda p-3">
            <Registro nota={n} autor={autorNome(n.author_id)} />
            {adendos(n.id).map((ad) => (
              <div key={ad.id} className="mt-2 ml-4 border-l-2 border-marca pl-3">
                <Registro nota={ad} autor={autorNome(ad.author_id)} adendo />
              </div>
            ))}
            {meu && <Adendo nota={n} aoSalvar={aoMudar} />}
          </li>
        ))}
      </ul>
      {aberto && meu && (
        <div className="nao-imprimir mt-3 flex flex-col gap-2">
          <AreaTexto rotulo="Nova evolução" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Procedimentos, achados, orientações…" />
          <div className="flex justify-end">
            <Botao onClick={() => evoluir.mutate()} disabled={!texto.trim()} carregando={evoluir.isPending}>
              Registrar e assinar
            </Botao>
          </div>
        </div>
      )}
    </Cartao>
  );
}

function Registro({ nota, autor, adendo = false }: { nota: Nota; autor: string; adendo?: boolean }) {
  const assinatura = nota.signatures[0];
  return (
    <div>
      <p className="text-xs text-texto-suave">
        {adendo ? "Adendo" : "Evolução"} · {dataHoraBR(nota.performed_at)} · {autor}
        {nota.created_at.slice(0, 16) !== nota.performed_at.slice(0, 16) && ` · registrada em ${dataHoraBR(nota.created_at)}`}
      </p>
      <p className="text-sm whitespace-pre-wrap">{nota.content}</p>
      {assinatura && (
        <p className="mt-1 font-mono text-[10px] break-all text-texto-suave">
          Assinatura eletrônica simples · SHA-256 {nota.content_hash.slice(0, 16)}…
        </p>
      )}
    </div>
  );
}

function Adendo({ nota, aoSalvar }: { nota: Nota; aoSalvar: () => void }) {
  const [aberto, setAberto] = useState(false);
  const [texto, setTexto] = useState("");
  const salvar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/prontuario/evolucoes/{note_id}/adendos", {
          params: { path: { note_id: nota.id } },
          body: { content: texto },
        }),
      ),
    onSuccess: () => {
      setTexto("");
      setAberto(false);
      aoSalvar();
    },
  });
  if (!aberto) {
    return (
      <button type="button" className="nao-imprimir mt-2 min-h-9 text-sm font-semibold text-marca" onClick={() => setAberto(true)}>
        + Adendo (correção)
      </button>
    );
  }
  return (
    <div className="nao-imprimir mt-2 flex flex-col gap-2">
      {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
      <AreaTexto rotulo="Adendo" value={texto} onChange={(e) => setTexto(e.target.value)} />
      <div className="flex justify-end gap-2">
        <Botao variante="secundario" onClick={() => setAberto(false)}>
          Cancelar
        </Botao>
        <Botao onClick={() => salvar.mutate()} disabled={!texto.trim()} carregando={salvar.isPending}>
          Registrar adendo
        </Botao>
      </div>
    </div>
  );
}
