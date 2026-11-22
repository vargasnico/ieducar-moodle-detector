"""Caso de uso RodarCiclo com i-Educar e publicador em memória e o adaptador SQLite."""

import sqlite3

import pytest

from detector.adaptadores.sqlite import SnapshotSqlite
from detector.aplicacao.rodar_ciclo import RodarCiclo
from detector.dominio.modelos import Componente, Escola, Turma


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class IEducarFalso:
    def __init__(self) -> None:
        self.turmas = [Turma(10, "1º ano A", 2026, 1, (5,), True)]
        self.fora_do_ar = False

    async def listar_escolas(self):
        if self.fora_do_ar:
            raise ConnectionError("i-Educar fora do ar")
        return [Escola(1, "Escola", True)]

    async def ano_letivo_em_andamento(self, escola_id):
        return 2026

    async def listar_turmas(self, ano, escolas):
        return self.turmas

    async def listar_componentes(self, escola_id, serie_id, ano):
        return [Componente(1, "Português")]

    async def listar_servidores(self):
        return []

    async def obter_servidor(self, servidor_id):
        return None

    async def listar_vinculos(self, ano, escolas):
        return []

    async def listar_alunos(self, ano, escolas):
        return []

    async def listar_matriculas(self, ano, escolas):
        return []

    async def listar_enturmacoes(self, ano, escolas):
        return []

    async def listar_dispensas(self, escolas):
        return []


class PublicadorFalso:
    def __init__(self) -> None:
        self.publicadas = []
        self.falhar = False

    async def publicar(self, mensagem) -> None:
        if self.falhar:
            raise ConnectionError("RabbitMQ fora")
        self.publicadas.append(mensagem)


@pytest.fixture
def ciclo():
    ieducar, publicador = IEducarFalso(), PublicadorFalso()
    snapshot = SnapshotSqlite(sqlite3.connect(":memory:"))
    return RodarCiclo(ieducar, snapshot, publicador), ieducar, publicador, snapshot


@pytest.mark.anyio
async def test_publica_so_o_que_mudou(ciclo):
    rodar, ieducar, publicador, _ = ciclo
    await rodar()
    assert [m.tipo for m in publicador.publicadas] == ["ieducar.turma.alterada"]
    publicador.publicadas.clear()
    await rodar()
    assert publicador.publicadas == []
    ieducar.turmas = [Turma(10, "1º ano B", 2026, 1, (5,), True)]
    await rodar()
    assert publicador.publicadas[0].dados["nome"] == "1º ano B"


@pytest.mark.anyio
async def test_ieducar_fora_nao_publica_nada(ciclo):
    rodar, ieducar, publicador, snapshot = ciclo
    ieducar.fora_do_ar = True
    with pytest.raises(ConnectionError):
        await rodar()
    assert publicador.publicadas == [] and snapshot.hashes() == {}


@pytest.mark.anyio
async def test_falha_ao_publicar_nao_grava_o_snapshot(ciclo):
    """Publica antes de gravar: se a publicação falha, o próximo ciclo tenta de novo."""
    rodar, _, publicador, snapshot = ciclo
    publicador.falhar = True
    with pytest.raises(ConnectionError):
        await rodar()
    assert snapshot.hashes() == {}
