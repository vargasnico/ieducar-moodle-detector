"""Detecção de mudanças no i-Educar.

O i-Educar não publica eventos, então a cada ciclo o detector lê o ano letivo inteiro,
monta o estado de cada servidor, turma e aluno e compara (pelo hash) com o que
publicou da última vez (snapshot). Só o que mudou vira evento, com o estado completo
da entidade: quem consome não precisa consultar o i-Educar.

Ordem de gravação: primeiro publica os eventos, depois grava o snapshot.
- Se o i-Educar cair no meio da leitura, nada é publicado nem gravado; o próximo
  ciclo encontra todas as mudanças (cenário 1).
- Se o detector cair depois de publicar e antes de gravar, o próximo ciclo publica de
  novo os mesmos eventos; como os consumidores são idempotentes, não há problema
  (cenário 4). Nada se perde, no máximo se repete.
"""

import hashlib
import json
import logging
import sqlite3
import time
import uuid
from collections import defaultdict
from typing import Any

from detector.broker import Broker
from detector.ieducar import IEducarClient
from detector.logs import correlation_id
from detector.mensagem import Mensagem, agora
from detector.metricas import CICLOS, DURACAO_CICLO, EVENTOS

log = logging.getLogger(__name__)

# Turmas antes de servidores e alunos: os cursos tendem a ser criados antes das
# inscrições (se não forem, a inscrição espera na fila de retry).
ORDEM = ("turma", "servidor", "aluno")
EVENTO = {
    "turma": "ieducar.turma.alterada",
    "servidor": "ieducar.servidor.alterado",
    "aluno": "ieducar.aluno.alterado",
}


class Detector:
    def __init__(
        self,
        db: sqlite3.Connection,
        ieducar: IEducarClient,
        broker: Broker,
        escola_id: int | None = None,
        ano_letivo: int | None = None,
    ) -> None:
        self.db = db
        self.ieducar = ieducar
        self.broker = broker
        self.escola_id = escola_id
        self.ano_letivo = ano_letivo
        db.execute(
            "CREATE TABLE IF NOT EXISTS snapshot (chave TEXT PRIMARY KEY, tipo TEXT, hash TEXT)"
        )

    async def ciclo(self, completo: bool = False) -> dict[str, Any]:
        """Um ciclo de detecção. Com `completo` publica todas as entidades, mudadas ou
        não (reenvia tudo ao Moodle)."""
        cid = str(uuid.uuid4())
        correlation_id.set(cid)
        inicio, iniciado_em = time.perf_counter(), agora()
        log.info("Ciclo de detecção iniciado (completo=%s)", completo)
        try:
            atuais = await self._ler()
            contagem = await self._publicar_mudancas(cid, iniciado_em, atuais, completo)
        except Exception as exc:
            CICLOS.labels("falha").inc()
            log.error("Ciclo de detecção falhou: %r", exc)
            raise
        finally:
            DURACAO_CICLO.observe(time.perf_counter() - inicio)
        CICLOS.labels("sucesso").inc()
        log.info("Ciclo de detecção concluído: %s", contagem)
        return {"correlation_id": cid, "eventos": contagem}

    async def _publicar_mudancas(
        self, cid: str, iniciado_em: Any, atuais: dict[str, tuple[str, dict]], completo: bool
    ) -> dict[str, int]:
        anteriores = {c: h for c, h in self.db.execute("SELECT chave, hash FROM snapshot")}
        contagem: dict[str, int] = defaultdict(int)
        gravar: list[tuple[str, str, str | None]] = []  # hash None = remover do snapshot

        async def publicar(tipo: str, dados: dict) -> None:
            await self.broker.publicar(
                Mensagem(tipo=tipo, correlation_id=cid, ciclo_iniciado_em=iniciado_em, dados=dados)
            )
            contagem[tipo] += 1
            EVENTOS.labels(tipo).inc()

        por_tipo = sorted(atuais.items(), key=lambda item: ORDEM.index(item[1][0]))
        for chave, (tipo, dados) in por_tipo:
            h = hashlib.sha256(json.dumps(dados, sort_keys=True).encode()).hexdigest()
            if completo or anteriores.get(chave) != h:
                await publicar(EVENTO[tipo], dados)
                gravar.append((chave, tipo, h))
        for chave in anteriores.keys() - atuais.keys():
            tipo, id_ = chave.split(":")
            # Sumiu do ano letivo no i-Educar (ex.: aluno saiu da escola).
            await publicar(f"ieducar.{tipo}.removido", {f"{tipo}_id": int(id_)})
            gravar.append((chave, tipo, None))

        with self.db:  # uma transação
            for chave, tipo, h in gravar:
                if h is None:
                    self.db.execute("DELETE FROM snapshot WHERE chave = ?", (chave,))
                else:
                    self.db.execute(
                        "INSERT OR REPLACE INTO snapshot VALUES (?, ?, ?)", (chave, tipo, h)
                    )
        return dict(contagem)

    async def _escopo(self) -> tuple[list[int], int]:
        if self.escola_id is not None:
            escolas = [self.escola_id]
        else:
            escolas = [e.escola_id for e in await self.ieducar.listar_escolas() if e.ativo]
        if not escolas:
            raise RuntimeError("Nenhuma escola ativa no i-Educar.")
        ano = self.ano_letivo or await self.ieducar.ano_letivo_em_andamento(escolas[0])
        if ano is None:
            raise RuntimeError("Nenhum ano letivo em andamento na escola.")
        return escolas, ano

    async def _ler(self) -> dict[str, tuple[str, dict]]:
        """Estado atual de cada entidade do ano letivo: chave → (tipo, dados)."""
        ie = self.ieducar
        escolas, ano = await self._escopo()
        cache: dict[tuple[int, int], list[dict]] = {}

        async def componentes(escola_id: int, serie_id: int) -> list[dict]:
            if (escola_id, serie_id) not in cache:
                cache[(escola_id, serie_id)] = [
                    {"id": c.componente_id, "nome": c.nome}
                    for c in await ie.listar_componentes(escola_id, serie_id, ano)
                ]
            return cache[(escola_id, serie_id)]

        atuais: dict[str, tuple[str, dict]] = {}

        # Turmas, com os componentes das suas séries (curso = turma × componente).
        for t in await ie.listar_turmas(ano, escolas):
            comps: dict[int, str] = {}
            if t.ativo:
                for serie_id in t.series:
                    for c in await componentes(t.escola_id, serie_id):
                        comps.setdefault(c["id"], c["nome"])
            atuais[f"turma:{t.turma_id}"] = (
                "turma",
                {
                    "turma_id": t.turma_id,
                    "nome": t.nome,
                    "ano": ano,
                    "ativa": t.ativo,
                    "componentes": [{"id": i, "nome": n} for i, n in sorted(comps.items())],
                },
            )

        # Servidores, com os vínculos ativos (turma e componentes) do ano.
        vinculos: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        for v in await ie.listar_vinculos(ano, escolas):
            if v.ativo:
                vinculos[v.servidor_id][v.turma_id].update(v.componentes)
        for s in await ie.listar_servidores():
            # A listagem não traz o e-mail; o detalhe traz.
            detalhe = await ie.obter_servidor(s.servidor_id) or s
            atuais[f"servidor:{s.servidor_id}"] = (
                "servidor",
                {
                    "servidor_id": s.servidor_id,
                    "nome": detalhe.nome,
                    "cpf": "".join(ch for ch in detalhe.cpf or "" if ch.isdigit()) or None,
                    "email": detalhe.email,
                    "ativo": s.ativo,
                    "vinculos": [
                        {"turma_id": turma_id, "componentes": sorted(c)}
                        for turma_id, c in sorted(vinculos[s.servidor_id].items())
                    ],
                },
            )

        # Alunos, com as turmas em que estão e os componentes que cursam em cada uma
        # (os da série, menos os de dispensa).
        alunos = {a.aluno_id: a for a in await ie.listar_alunos(ano, escolas)}
        matriculas = {
            m.matricula_id: m
            for m in await ie.listar_matriculas(ano, escolas)
            if m.ativo and m.aluno_id in alunos
        }
        dispensas: dict[int, set[int]] = defaultdict(set)
        for d in await ie.listar_dispensas(escolas):
            if d.ativa:
                dispensas[d.matricula_id].add(d.componente_id)
        turmas_do_aluno: dict[int, list[dict]] = defaultdict(list)
        for e in await ie.listar_enturmacoes(ano, escolas):
            m = matriculas.get(e.matricula_id)
            if e.ativa and m:
                da_serie = {c["id"] for c in await componentes(m.escola_id, e.serie_id)}
                turmas_do_aluno[m.aluno_id].append(
                    {
                        "turma_id": e.turma_id,
                        "componentes": sorted(da_serie - dispensas[m.matricula_id]),
                    }
                )
        for a in alunos.values():
            atuais[f"aluno:{a.aluno_id}"] = (
                "aluno",
                {
                    "aluno_id": a.aluno_id,
                    "nome": a.nome_social or a.nome,
                    "ativo": a.ativo,
                    "turmas": sorted(turmas_do_aluno[a.aluno_id], key=lambda x: x["turma_id"]),
                },
            )
        return atuais
