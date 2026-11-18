import { lazy, Suspense, type ReactNode } from "react";
import { Route, Routes } from "react-router-dom";

import { Carregando } from "./components/ui";
import AppLayout from "./layout/AppLayout";
import Inicio from "./pages/Inicio";
import Login from "./pages/Login";
import NaoEncontrado from "./pages/NaoEncontrado";

// Telas carregadas sob demanda (o 3D, principalmente, é pesado).
const Pacientes = lazy(() => import("./pages/pacientes/Pacientes"));
const Paciente = lazy(() => import("./pages/pacientes/Paciente"));
const Agenda = lazy(() => import("./pages/agenda/Agenda"));
const Alertas = lazy(() => import("./pages/Alertas"));
const Gestao = lazy(() => import("./pages/gestao/Gestao"));
const Precificacao = lazy(() => import("./pages/precificacao/Precificacao"));
const Estoque = lazy(() => import("./pages/estoque/Estoque"));
const Financeiro = lazy(() => import("./pages/financeiro/Financeiro"));
const Configuracoes = lazy(() => import("./pages/config/Configuracoes"));

function Tela({ children }: { children: ReactNode }) {
  return <Suspense fallback={<Carregando />}>{children}</Suspense>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<AppLayout />}>
        <Route index element={<Inicio />} />
        <Route path="pacientes" element={<Tela><Pacientes /></Tela>} />
        <Route path="pacientes/:id/*" element={<Tela><Paciente /></Tela>} />
        <Route path="agenda" element={<Tela><Agenda /></Tela>} />
        <Route path="alertas" element={<Tela><Alertas /></Tela>} />
        <Route path="gestao" element={<Tela><Gestao /></Tela>} />
        <Route path="precificacao/*" element={<Tela><Precificacao /></Tela>} />
        <Route path="estoque" element={<Tela><Estoque /></Tela>} />
        <Route path="financeiro" element={<Tela><Financeiro /></Tela>} />
        <Route path="configuracoes" element={<Tela><Configuracoes /></Tela>} />
        <Route path="*" element={<NaoEncontrado />} />
      </Route>
    </Routes>
  );
}
