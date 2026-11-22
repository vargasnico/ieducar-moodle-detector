"""Adaptador de entrada por tempo: roda um ciclo a cada `intervalo` segundos. Um ciclo
por vez (o mesmo lock é usado pela rota POST /ciclos)."""

import asyncio
import contextlib

from detector.aplicacao.rodar_ciclo import RodarCiclo


async def agendar(rodar_ciclo: RodarCiclo, lock: asyncio.Lock, intervalo: int) -> None:
    while True:
        with contextlib.suppress(Exception):  # a falha já foi registrada no log
            async with lock:
                await rodar_ciclo()
        await asyncio.sleep(intervalo)
