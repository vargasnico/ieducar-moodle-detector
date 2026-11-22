"""Adaptador de entrada HTTP: health check, métricas e disparo manual de um ciclo."""

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def criar_app(lifespan) -> FastAPI:
    app = FastAPI(title="Detector de mudanças do i-Educar", lifespan=lifespan)

    @app.get("/health", tags=["status"])
    def health(request: Request) -> JSONResponse:
        """O serviço está no ar e conectado ao RabbitMQ."""
        ok = request.app.state.broker.conectado
        return JSONResponse(
            {"status": "ok" if ok else "sem broker", "broker": ok}, status_code=200 if ok else 503
        )

    @app.get("/metrics", tags=["status"], include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/ciclos", tags=["detecção"])
    async def ciclo(request: Request, completo: bool = False) -> dict:
        """Roda um ciclo agora. Com `completo=true` reenvia todas as entidades."""
        lock = request.app.state.lock
        if lock.locked():
            raise HTTPException(409, "Já existe um ciclo em andamento.")
        async with lock:
            try:
                return await request.app.state.rodar_ciclo(completo)
            except Exception as exc:
                raise HTTPException(502, f"Falha ao ler o i-Educar: {exc!r}") from exc

    return app
