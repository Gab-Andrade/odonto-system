import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { api, mensagemErro, type Schemas } from "../api/client";
import { sessaoValida, useSessao, type Papel } from "../auth/sessao";
import { Aviso, Botao, Campo } from "../components/ui";

type Clinica = Schemas["ClinicOption"];

export default function Login() {
  const sessao = useSessao();
  const navegar = useNavigate();
  const local = useLocation();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [clinicas, setClinicas] = useState<Clinica[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  if (sessaoValida(sessao)) {
    const destino = (local.state as { de?: string } | null)?.de ?? "/";
    return <Navigate to={destino} replace />;
  }

  async function entrar(clinicId?: string) {
    setErro(null);
    setEnviando(true);
    try {
      const res = await api.POST("/auth/login", {
        body: { email, password: senha, clinic_id: clinicId ?? null },
      });
      if (res.response.status === 409) {
        // Usuário em mais de uma clínica: a API devolve a lista para escolher.
        setClinicas((res.error as unknown as Schemas["ClinicSelectionResponse"]).clinics);
        return;
      }
      if (!res.data) {
        setErro(mensagemErro(res.error, "E-mail ou senha inválidos."));
        return;
      }
      sessao.entrar({
        token: res.data.access_token,
        expiraEmSegundos: res.data.expires_in,
        clinica: { id: res.data.clinic.id, nome: res.data.clinic.name },
        papel: res.data.role as Papel,
      });
      const me = await api.GET("/auth/me");
      if (me.data) {
        sessao.definirUsuario({ id: me.data.user_id, nome: me.data.full_name, email: me.data.email });
      }
      navegar((local.state as { de?: string } | null)?.de ?? "/", { replace: true });
    } catch (e) {
      setErro(mensagemErro(e, "Não foi possível conectar à API. Ela está rodando?"));
    } finally {
      setEnviando(false);
    }
  }

  function enviar(ev: FormEvent) {
    ev.preventDefault();
    void entrar();
  }

  return (
    <main className="flex min-h-full items-center justify-center p-4">
      <div className="w-full max-w-md rounded-2xl border border-borda bg-painel p-6 shadow-lg">
        <div className="mb-6 flex items-center gap-3">
          <img src="/icone.svg" alt="" className="size-12" />
          <div>
            <h1 className="text-xl font-bold">Odonto System</h1>
            <p className="text-sm text-texto-suave">Entre com seu e-mail e senha.</p>
          </div>
        </div>

        {sessao.aviso && !erro && <Aviso tom="alerta">{sessao.aviso}</Aviso>}
        {erro && <Aviso tom="perigo">{erro}</Aviso>}

        {clinicas ? (
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
        ) : (
          <form onSubmit={enviar} className="mt-4 flex flex-col gap-4">
            <Campo
              rotulo="E-mail"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Campo
              rotulo="Senha"
              type="password"
              autoComplete="current-password"
              required
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
            />
            <Botao type="submit" carregando={enviando}>
              Entrar
            </Botao>
          </form>
        )}
      </div>
    </main>
  );
}
