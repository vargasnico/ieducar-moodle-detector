"""O detector publica só o que mudou desde o último ciclo (sem rede: i-Educar e
broker falsos)."""

import sqlite3

import pytest

from detector.deteccao import Detector


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class BrokerFalso:
    def __init__(self) -> None:
        self.publicadas = []

    async def publicar(self, mensagem) -> None:
        self.publicadas.append(mensagem)


TURMA = {"turma_id": 10, "nome": "1º ano A", "ano": 2026, "ativa": True, "componentes": []}
ALUNO = {"aluno_id": 20, "nome": "Carla", "ativo": True, "turmas": []}


@pytest.fixture
def detector():
    broker = BrokerFalso()
    d = Detector(sqlite3.connect(":memory:"), None, broker)  # type: ignore[arg-type]
    estado = {"turma:10": ("turma", TURMA), "aluno:20": ("aluno", ALUNO)}

    async def ler():
        return dict(estado)

    d._ler = ler  # type: ignore[method-assign]
    return d, broker, estado


def tipos(broker) -> list[str]:
    return [m.tipo for m in broker.publicadas]


@pytest.mark.anyio
async def test_primeiro_ciclo_publica_tudo_com_turmas_primeiro(detector):
    d, broker, _ = detector
    await d.ciclo()
    assert tipos(broker) == ["ieducar.turma.alterada", "ieducar.aluno.alterado"]
    assert len({m.correlation_id for m in broker.publicadas}) == 1


@pytest.mark.anyio
async def test_sem_mudanca_nao_publica_nada(detector):
    d, broker, _ = detector
    await d.ciclo()
    broker.publicadas.clear()
    await d.ciclo()
    assert broker.publicadas == []


@pytest.mark.anyio
async def test_publica_so_o_que_mudou_e_o_que_sumiu(detector):
    d, broker, estado = detector
    await d.ciclo()
    broker.publicadas.clear()
    estado["turma:10"] = ("turma", {**TURMA, "nome": "1º ano B"})
    del estado["aluno:20"]
    await d.ciclo()
    assert tipos(broker) == ["ieducar.turma.alterada", "ieducar.aluno.removido"]


@pytest.mark.anyio
async def test_completo_publica_tudo_de_novo(detector):
    d, broker, _ = detector
    await d.ciclo()
    broker.publicadas.clear()
    await d.ciclo(completo=True)
    assert len(broker.publicadas) == 2


@pytest.mark.anyio
async def test_falha_ao_publicar_nao_grava_o_snapshot(detector):
    """Publica antes de gravar: se a publicação falha, o próximo ciclo tenta de novo."""
    d, broker, _ = detector

    async def falha(_):
        raise ConnectionError("RabbitMQ fora")

    broker.publicar = falha
    with pytest.raises(ConnectionError):
        await d.ciclo()
    broker.publicar = BrokerFalso().publicar
    assert d.db.execute("SELECT COUNT(*) FROM snapshot").fetchone()[0] == 0
