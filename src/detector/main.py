"""Serviço detector: descobre o que mudou no i-Educar e publica eventos.

Único serviço que fala com o i-Educar. Dono do banco detector.db (snapshot).
"""

import asyncio
import contextlib
import logging
import os
import sqlite3
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException

from detector.api import rotas_comuns
from detector.broker import Broker
from detector.deteccao import Detector
from detector.ieducar import IEducarClient
from detector.logs import configurar_logs

log = logging.getLogger(__name__)


def _int(nome: str) -> int | None:
    return int(os.environ[nome]) if os.environ.get(nome) else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    configurar_logs("detector")
    db = sqlite3.connect(os.environ.get("DATABASE_PATH", "data/detector.db"))
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
    detector = Detector(db, ieducar, broker, _int("IEDUCAR_ESCOLA_ID"), _int("IEDUCAR_ANO_LETIVO"))
    app.state.broker, app.state.detector = broker, detector
    app.state.lock = asyncio.Lock()  # um ciclo por vez

    async def agendar(intervalo: int) -> None:
        while True:
            with contextlib.suppress(Exception):  # a falha já foi registrada no log
                async with app.state.lock:
                    await detector.ciclo()
            await asyncio.sleep(intervalo)

    intervalo = _int("INTERVALO_SEGUNDOS") or 60
    tarefa = asyncio.create_task(agendar(intervalo))
    yield
    tarefa.cancel()
    await http.aclose()
    await broker.fechar()


app = FastAPI(title="Detector de mudanças do i-Educar", lifespan=lifespan)
rotas_comuns(app)


@app.post("/ciclos", tags=["detecção"])
async def ciclo(completo: bool = False) -> dict:
    """Roda um ciclo agora. Com `completo=true` reenvia todas as entidades."""
    if app.state.lock.locked():
        raise HTTPException(409, "Já existe um ciclo em andamento.")
    async with app.state.lock:
        try:
            return await app.state.detector.ciclo(completo)
        except Exception as exc:
            raise HTTPException(502, f"Falha ao ler o i-Educar: {exc!r}") from exc
