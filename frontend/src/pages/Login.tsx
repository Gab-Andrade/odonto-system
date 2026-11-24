import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { api, mensagemErro, type Schemas } from "../api/client";
import { sessaoValida, useSessao, type Papel } from "../auth/sessao";
import { Aviso, Botao, Campo } from "../components/ui";

type Clinica = Schemas["ClinicOption"];
type Token = Schemas["TokenResponse"];

/**
 * Entrar, definir a própria senha no primeiro acesso (a senha recebida da clínica é
 * aleatória e só serve para isso) e aceitar o convite de outra clínica com o código que
 * ela entregou.
 */
type Modo = "entrar" | "definir" | "codigo";

export default function Login() {
  const sessao = useSessao();
  const navegar = useNavigate();
  const local = useLocation();
  const [modo, setModo] = useState<Modo>("entrar");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [nova, setNova] = useState("");
  const [confirma, setConfirma] = useState("");
  const [codigo, setCodigo] = useState("");
  const [clinicas, setClinicas] = useState<Clinica[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  if (sessaoValida(sessao)) {
    const destino = (local.state as { de?: string } | null)?.de ?? "/";
    return <Navigate to={destino} replace />;
  }

  async function concluir(dados: Token) {
    sessao.entrar({
      token: dados.access_token,
      expiraEmSegundos: dados.expires_in,
      clinica: { id: dados.clinic.id, nome: dados.clinic.name },
      papel: dados.role as Papel,
    });
    const me = await api.GET("/auth/me");
    if (me.data) {
      sessao.definirUsuario({ id: me.data.user_id, nome: me.data.full_name, email: me.data.email });
    }
    navegar((local.state as { de?: string } | null)?.de ?? "/", { replace: true });
  }

  async function tentar(acao: () => Promise<void>, padrao: string) {
    setErro(null);
    setInfo(null);
    setEnviando(true);
    try {
      await acao();
    } catch (e) {
      setErro(mensagemErro(e, padrao));
    } finally {
      setEnviando(false);
    }
  }

  function entrar(clinicId?: string, senhaUsada = senha) {
    return tentar(async () => {
      const res = await api.POST("/auth/login", {
        body: { email, password: senhaUsada, clinic_id: clinicId ?? null },
      });
      if (res.response.status === 409) {
        // Usuário em mais de uma clínica: a API devolve a lista para escolher.
        setClinicas((res.error as unknown as Schemas["ClinicSelectionResponse"]).clinics);
        return;
      }
      if (res.response.status === 403) {
        setModo("definir");
        setInfo("Esta é uma senha provisória. Defina uma senha sua para continuar.");
        return;
      }
      if (!res.data) {
        setErro(mensagemErro(res.error, "E-mail ou senha inválidos."));
        return;
      }
      await concluir(res.data);
    }, "Não foi possível conectar à API. Ela está rodando?");
  }

  function definir(ev: FormEvent) {
    ev.preventDefault();
    if (nova !== confirma) {
      setErro("As duas senhas novas não são iguais.");
      return;
    }
    void tentar(async () => {
      const res = await api.POST("/auth/primeiro-acesso", {
        body: { email, current_password: senha, new_password: nova },
      });
      if (res.response.status === 409 && (res.error as { clinics?: Clinica[] } | undefined)?.clinics) {
        // A senha já foi trocada; falta escolher a clínica.
        setSenha(nova);
        setModo("entrar");
        setClinicas((res.error as unknown as Schemas["ClinicSelectionResponse"]).clinics);
        return;
      }
      if (!res.data) {
        setErro(mensagemErro(res.error, "Não foi possível definir a senha."));
        return;
      }
      await concluir(res.data);
    }, "Não foi possível definir a senha.");
  }

  function aceitar(ev: FormEvent) {
    ev.preventDefault();
    void tentar(async () => {
      const res = await api.POST("/auth/vinculos/aceitar", {
        body: { email, password: senha, code: codigo },
      });
      if (res.response.status === 403) {
        setModo("definir");
        setInfo("Antes, defina uma senha sua. Depois, volte e digite o código.");
        return;
      }
      if (!res.response.ok) {
        setErro(mensagemErro(res.error, "Não foi possível aceitar o convite."));
        return;
      }
      setCodigo("");
      setModo("entrar");
      setInfo("Pronto! Agora entre e escolha a nova clínica.");
    }, "Não foi possível aceitar o convite.");
  }

  const campoEmail = (
    <Campo
      rotulo="E-mail"
      type="email"
      autoComplete="username"
      required
      value={email}
      onChange={(e) => setEmail(e.target.value)}
    />
  );
  const campoSenha = (rotulo: string) => (
    <Campo
      rotulo={rotulo}
      type="password"
      autoComplete="current-password"
      required
      value={senha}
      onChange={(e) => setSenha(e.target.value)}
    />
  );

  return (
    <main className="flex min-h-full items-center justify-center p-4">
      <div className="w-full max-w-md rounded-2xl border border-borda bg-painel p-6 shadow-lg">
        <div className="mb-6 flex items-center gap-3">
          <img src="/icone.svg" alt="" className="size-12" />
          <div>
            <h1 className="text-xl font-bold">Odonto System</h1>
            <p className="text-sm text-texto-suave">
              {modo === "entrar" && "Entre com seu e-mail e senha."}
              {modo === "definir" && "Defina a sua senha."}
              {modo === "codigo" && "Aceitar o convite de uma clínica."}
            </p>
          </div>
        </div>

        {sessao.aviso && !erro && !info && <Aviso tom="alerta">{sessao.aviso}</Aviso>}
        {info && !erro && <Aviso tom="sucesso">{info}</Aviso>}
        {erro && <Aviso tom="perigo">{erro}</Aviso>}

        {modo === "entrar" && clinicas && (
          <div className="mt-4 flex flex-col gap-2">
            <p className="text-sm font-medium">Você atende em mais de uma clínica. Qual agora?</p>
            {clinicas.map((c) => (
              <Botao
                key={c.id}
                variante="secundario"
                className="justify-start"
                carregando={enviando}
                onClick={() => void entrar(c.id)}
              >
                {c.name}
              </Botao>
            ))}
            <Botao variante="fantasma" onClick={() => setClinicas(null)}>
              Voltar
            </Botao>
          </div>
        )}

        {modo === "entrar" && !clinicas && (
          <form
            onSubmit={(ev) => {
              ev.preventDefault();
              void entrar();
            }}
            className="mt-4 flex flex-col gap-4"
          >
            {campoEmail}
            {campoSenha("Senha")}
            <Botao type="submit" carregando={enviando}>
              Entrar
            </Botao>
            <Botao variante="fantasma" onClick={() => setModo("codigo")}>
              Recebi um código de uma clínica
            </Botao>
          </form>
        )}

        {modo === "definir" && (
          <form onSubmit={definir} className="mt-4 flex flex-col gap-4">
            {campoEmail}
            {campoSenha("Senha provisória (recebida da clínica)")}
            <Campo
              rotulo="Nova senha"
              type="password"
              autoComplete="new-password"
              required
              minLength={10}
              dica="Pelo menos 10 caracteres."
              value={nova}
              onChange={(e) => setNova(e.target.value)}
            />
            <Campo
              rotulo="Repita a nova senha"
              type="password"
              autoComplete="new-password"
              required
              minLength={10}
              value={confirma}
              onChange={(e) => setConfirma(e.target.value)}
            />
            <Botao type="submit" carregando={enviando}>
              Salvar e entrar
            </Botao>
            <Botao variante="fantasma" onClick={() => setModo("entrar")}>
              Voltar
            </Botao>
          </form>
        )}

        {modo === "codigo" && (
          <form onSubmit={aceitar} className="mt-4 flex flex-col gap-4">
            <p className="text-sm text-texto-suave">
              Se você já usa o sistema em outra clínica, a nova clínica entrega a você um código. Entre com o seu
              e-mail e a sua senha de sempre e digite o código.
            </p>
            {campoEmail}
            {campoSenha("Sua senha")}
            <Campo
              rotulo="Código da clínica"
              required
              autoComplete="off"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
            />
            <Botao type="submit" carregando={enviando}>
              Aceitar convite
            </Botao>
            <Botao variante="fantasma" onClick={() => setModo("entrar")}>
              Voltar
            </Botao>
          </form>
        )}
      </div>
    </main>
  );
}
