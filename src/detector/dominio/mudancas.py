"""Decide quais eventos publicar comparando o estado atual com o último publicado.

O i-Educar não publica eventos, então o detector compara o hash do estado de cada
entidade com o do snapshot (o último que ele publicou). Só o que mudou vira evento;
o que sumiu vira um evento de remoção. Função pura.
"""

import hashlib
import json
from dataclasses import dataclass, field

from detector.dominio.estado import Estado

# Turmas antes de servidores e alunos: os cursos tendem a ser criados antes das
# inscrições (se não forem, a inscrição espera na fila de retry do publicador).
ORDEM = ("turma", "servidor", "aluno")
# Nomes dos eventos, exatamente como no catálogo de mensagens (o contrato com o
# sincronizador). Escritos por extenso: "turma" é feminino (alterada, removida).
ALTERADO = {
    "turma": "ieducar.turma.alterada",
    "servidor": "ieducar.servidor.alterado",
    "aluno": "ieducar.aluno.alterado",
}
REMOVIDO = {
    "turma": "ieducar.turma.removida",
    "servidor": "ieducar.servidor.removido",
    "aluno": "ieducar.aluno.removido",
}


@dataclass(frozen=True)
class Evento:
    tipo: str
    dados: dict


@dataclass
class Mudancas:
    eventos: list[Evento] = field(default_factory=list)
    # Snapshot novo: chave → (tipo, hash); hash None = remover do snapshot.
    snapshot: dict[str, tuple[str, str | None]] = field(default_factory=dict)


def hash_do_estado(dados: dict) -> str:
    return hashlib.sha256(json.dumps(dados, sort_keys=True).encode()).hexdigest()


def detectar(atual: Estado, anterior: dict[str, str], completo: bool = False) -> Mudancas:
    """`anterior` é o snapshot (chave → hash). Com `completo`, todas as entidades
    viram evento, mudadas ou não (reenvia tudo ao Moodle)."""
    mudancas = Mudancas()
    for chave, (tipo, dados) in sorted(atual.items(), key=lambda item: ORDEM.index(item[1][0])):
        h = hash_do_estado(dados)
        if completo or anterior.get(chave) != h:
            mudancas.eventos.append(Evento(ALTERADO[tipo], dados))
            mudancas.snapshot[chave] = (tipo, h)
    for chave in sorted(anterior.keys() - atual.keys()):
        tipo, id_ = chave.split(":")
        # Sumiu do ano letivo no i-Educar (ex.: aluno saiu da escola).
        mudancas.eventos.append(Evento(REMOVIDO[tipo], {f"{tipo}_id": int(id_)}))
        mudancas.snapshot[chave] = (tipo, None)
    return mudancas
