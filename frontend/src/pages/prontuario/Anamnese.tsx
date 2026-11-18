import { Cartao } from "../../components/ui";

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export default function Tela(_: { pacienteId:  string }) {
  return (
    <Cartao titulo="Anamnese">
      <p className="text-sm text-texto-suave">Esta aba entra numa próxima etapa do frontend.</p>
    </Cartao>
  );
}
