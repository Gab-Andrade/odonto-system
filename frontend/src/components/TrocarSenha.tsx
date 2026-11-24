import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok } from "../api/client";
import { useSessao, type Papel } from "../auth/sessao";
import Modal from "./Modal";
import { Aviso, Botao, Campo } from "./ui";

/** Troca a própria senha. As outras sessões caem; esta recebe um token novo da API. */
export default function TrocarSenha({ aoFechar }: { aoFechar: () => void }) {
  const entrar = useSessao((s) => s.entrar);
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [confirma, setConfirma] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [feito, setFeito] = useState(false);

  const trocar = useMutation({
    mutationFn: async () =>
      ok(await api.POST("/auth/senha", { body: { current_password: atual, new_password: nova } })),
    onSuccess: (d) => {
      entrar({
        token: d.access_token,
        expiraEmSegundos: d.expires_in,
        clinica: { id: d.clinic.id, nome: d.clinic.name },
        papel: d.role as Papel,
      });
      setFeito(true);
    },
    onError: (e) => setErro(e.message),
  });

  return (
    <Modal titulo="Trocar senha" aberto aoFechar={aoFechar}>
      {feito ? (
        <div className="flex flex-col gap-4">
          <Aviso tom="sucesso">Senha trocada. Nos outros aparelhos, será preciso entrar de novo.</Aviso>
          <Botao onClick={aoFechar}>Fechar</Botao>
        </div>
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setErro(null);
            if (nova !== confirma) {
              setErro("As duas senhas novas não são iguais.");
              return;
            }
            trocar.mutate();
          }}
        >
          <Campo
            rotulo="Senha atual"
            type="password"
            autoComplete="current-password"
            required
            value={atual}
            onChange={(e) => setAtual(e.target.value)}
          />
          <Campo
            rotulo="Nova senha"
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            dica="Pelo menos 10 caracteres. Vale em todas as clínicas em que você atua."
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
          {erro && <Aviso tom="perigo">{erro}</Aviso>}
          <div className="flex justify-end gap-2">
            <Botao variante="secundario" onClick={aoFechar}>
              Cancelar
            </Botao>
            <Botao type="submit" carregando={trocar.isPending}>
              Trocar
            </Botao>
          </div>
        </form>
      )}
    </Modal>
  );
}
