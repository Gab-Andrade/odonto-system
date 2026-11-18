import { Cartao, Titulo } from "./ui";

/** Tela ainda não construída nesta etapa do frontend. */
export default function EmBreve({ titulo }: { titulo: string }) {
  return (
    <div>
      <Titulo>{titulo}</Titulo>
      <Cartao>
        <p className="text-sm text-texto-suave">
          Esta tela entra numa próxima etapa do frontend. A API já está pronta: veja em
          http://localhost:8000/docs.
        </p>
      </Cartao>
    </div>
  );
}
