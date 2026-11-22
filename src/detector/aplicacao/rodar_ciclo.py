"""Caso de uso: um ciclo de detecção.

1. Lê o ano letivo inteiro do i-Educar.
2. Pede ao domínio o estado de cada entidade e o que mudou desde o snapshot.
3. Publica os eventos e SÓ DEPOIS grava o snapshot.
   - Se o i-Educar cair no meio da leitura, nada é publicado nem gravado; o próximo
     ciclo encontra todas as mudanças (cenário 1).
   - Se o detector cair depois de publicar e antes de gravar, o próximo ciclo publica
     de novo os mesmos eventos; como os consumidores são idempotentes, não há problema
     (cenário 4). Nada se perde, no máximo se repete.
"""

import logging
import time
import uuid

from detector.dominio.estado import montar_estado, series_com_componentes
from detector.dominio.modelos import DadosDoAno
from detector.dominio.mudancas import detectar
from detector.infra.logs import correlation_id
from detector.infra.metricas import CICLOS, DURACAO_CICLO, EVENTOS
from detector.mensagem import Mensagem, agora
from detector.portas import IEducar, PublicadorDeEventos, Snapshot

log = logging.getLogger(__name__)


class RodarCiclo:
    def __init__(
        self,
        ieducar: IEducar,
        snapshot: Snapshot,
        publicador: PublicadorDeEventos,
        escola_id: int | None = None,
        ano_letivo: int | None = None,
    ) -> None:
        self.ieducar = ieducar
        self.snapshot = snapshot
        self.publicador = publicador
        self.escola_id = escola_id
        self.ano_letivo = ano_letivo

    async def __call__(self, completo: bool = False) -> dict:
        """Com `completo` publica todas as entidades, mudadas ou não."""
        cid = str(uuid.uuid4())
        correlation_id.set(cid)
        inicio, iniciado_em = time.perf_counter(), agora()
        log.info("Ciclo de detecção iniciado (completo=%s)", completo)
        try:
            dados = await self._ler()
            mudancas = detectar(montar_estado(dados), self.snapshot.hashes(), completo)
            contagem: dict[str, int] = {}
            for evento in mudancas.eventos:
                await self.publicador.publicar(
                    Mensagem(
                        tipo=evento.tipo,
                        correlation_id=cid,
                        ciclo_iniciado_em=iniciado_em,
                        dados=evento.dados,
                    )
                )
                contagem[evento.tipo] = contagem.get(evento.tipo, 0) + 1
                EVENTOS.labels(evento.tipo).inc()
            self.snapshot.gravar(mudancas.snapshot)
        except Exception as exc:
            CICLOS.labels("falha").inc()
            log.error("Ciclo de detecção falhou: %r", exc)
            raise
        finally:
            DURACAO_CICLO.observe(time.perf_counter() - inicio)
        CICLOS.labels("sucesso").inc()
        log.info("Ciclo de detecção concluído: %s", contagem)
        return {"correlation_id": cid, "eventos": contagem}

    async def _ler(self) -> DadosDoAno:
        ie = self.ieducar
        if self.escola_id is not None:
            escolas = [self.escola_id]
        else:
            escolas = [e.escola_id for e in await ie.listar_escolas() if e.ativo]
        if not escolas:
            raise RuntimeError("Nenhuma escola ativa no i-Educar.")
        ano = self.ano_letivo or await ie.ano_letivo_em_andamento(escolas[0])
        if ano is None:
            raise RuntimeError("Nenhum ano letivo em andamento na escola.")
        servidores = []
        for s in await ie.listar_servidores():
            # A listagem não traz o e-mail; o detalhe traz.
            servidores.append(await ie.obter_servidor(s.servidor_id) or s)
        dados = DadosDoAno(
            ano=ano,
            turmas=await ie.listar_turmas(ano, escolas),
            servidores=servidores,
            vinculos=await ie.listar_vinculos(ano, escolas),
            alunos=await ie.listar_alunos(ano, escolas),
            matriculas=await ie.listar_matriculas(ano, escolas),
            enturmacoes=await ie.listar_enturmacoes(ano, escolas),
            dispensas=await ie.listar_dispensas(escolas),
        )
        for escola_id, serie_id in sorted(series_com_componentes(dados)):
            dados.componentes[(escola_id, serie_id)] = await ie.listar_componentes(
                escola_id, serie_id, ano
            )
        return dados
