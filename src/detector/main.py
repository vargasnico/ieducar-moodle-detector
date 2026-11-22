"""Serviço detector: descobre o que mudou no i-Educar e publica eventos. Único serviço
que fala com o i-Educar.

Este arquivo só compõe as peças (arquitetura hexagonal):

    adaptadores/agendador.py ┐
    adaptadores/api.py ──────┴──▶ aplicacao/rodar_ciclo.py ──▶ dominio/
                                        │ portas.py
          adaptadores/ieducar.py ◀──────┤──▶ adaptadores/rabbitmq.py (eventos)
                                        └──▶ adaptadores/sqlite.py (snapshot)
"""

import asyncio
import os
import sqlite3
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from detector.adaptadores.agendador import agendar
from detector.adaptadores.api import criar_app
from detector.adaptadores.ieducar import IEducarClient
from detector.adaptadores.rabbitmq import Broker
from detector.adaptadores.sqlite import SnapshotSqlite
from detector.aplicacao.rodar_ciclo import RodarCiclo
from detector.infra.logs import configurar_logs


def _int(nome: str) -> int | None:
    return int(os.environ[nome]) if os.environ.get(nome) else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    configurar_logs("detector")
    snapshot = SnapshotSqlite(sqlite3.connect(os.environ.get("DATABASE_PATH", "data/detector.db")))
    broker = Broker(os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost/"), "detector")
    await broker.conectar()
    # Timeout: 3s para conectar, 10s para responder.
    http = httpx.AsyncClient(
        base_url=os.environ.get("IEDUCAR_URL", "http://localhost"),
        timeout=httpx.Timeout(10, connect=3),
    )
    ieducar = IEducarClient(
        http, os.environ.get("IEDUCAR_ACCESS_KEY", ""), _int("IEDUCAR_INSTITUICAO_ID") or 1
    )
    rodar_ciclo = RodarCiclo(
        ieducar, snapshot, broker, _int("IEDUCAR_ESCOLA_ID"), _int("IEDUCAR_ANO_LETIVO")
    )
    app.state.broker, app.state.rodar_ciclo = broker, rodar_ciclo
    app.state.lock = asyncio.Lock()  # um ciclo por vez
    tarefa = asyncio.create_task(
        agendar(rodar_ciclo, app.state.lock, _int("INTERVALO_SEGUNDOS") or 60)
    )
    yield
    tarefa.cancel()
    await http.aclose()
    await broker.fechar()


app = criar_app(lifespan)
