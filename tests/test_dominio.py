"""Domínio puro: montar o estado das entidades e detectar o que mudou."""

from detector.dominio.estado import montar_estado
from detector.dominio.modelos import (
    Aluno,
    Componente,
    DadosDoAno,
    Dispensa,
    Enturmacao,
    Matricula,
    Servidor,
    Turma,
    Vinculo,
)
from detector.dominio.mudancas import detectar

TURMA = {"turma_id": 10, "nome": "1º ano A", "ano": 2026, "ativa": True, "componentes": []}
ALUNO = {"aluno_id": 20, "nome": "Carla", "ativo": True, "turmas": []}


def dados() -> DadosDoAno:
    return DadosDoAno(
        ano=2026,
        turmas=[Turma(10, "1º ano A", 2026, 1, (5,), True)],
        servidores=[Servidor(7, "Ana", "111.222.333-44", True, "x", "ana@x")],
        vinculos=[Vinculo(1, 7, 10, (1,), True)],
        alunos=[Aluno(20, "Davi", "Dani", True)],
        matriculas=[Matricula(200, 20, 1, True)],
        enturmacoes=[Enturmacao(200, 10, 5, True)],
        dispensas=[Dispensa(200, 2, True)],
        componentes={(1, 5): [Componente(1, "Português"), Componente(2, "Matemática")]},
    )


def test_estado_tem_componentes_vinculos_nome_social_e_dispensas():
    estado = montar_estado(dados())
    assert [c["id"] for c in estado["turma:10"][1]["componentes"]] == [1, 2]
    assert estado["servidor:7"][1]["cpf"] == "11122233344"
    assert estado["servidor:7"][1]["vinculos"] == [{"turma_id": 10, "componentes": [1]}]
    aluno = estado["aluno:20"][1]
    assert aluno["nome"] == "Dani"  # nome social
    assert aluno["turmas"] == [{"turma_id": 10, "componentes": [1]}]  # sem Matemática


def test_primeira_vez_tudo_vira_evento_com_turmas_primeiro():
    atual = {"aluno:20": ("aluno", ALUNO), "turma:10": ("turma", TURMA)}
    m = detectar(atual, anterior={})
    assert [e.tipo for e in m.eventos] == ["ieducar.turma.alterada", "ieducar.aluno.alterado"]


def test_sem_mudanca_nada_vira_evento_e_completo_reenvia_tudo():
    atual = {"turma:10": ("turma", TURMA)}
    snapshot = {k: h for k, (_, h) in detectar(atual, {}).snapshot.items() if h}
    assert detectar(atual, snapshot).eventos == []
    assert len(detectar(atual, snapshot, completo=True).eventos) == 1


def test_o_que_sumiu_vira_remocao():
    m = detectar({}, anterior={"aluno:20": "abc"})
    assert [(e.tipo, e.dados) for e in m.eventos] == [("ieducar.aluno.removido", {"aluno_id": 20})]
    assert m.snapshot == {"aluno:20": ("aluno", None)}


def test_nomes_dos_eventos_seguem_o_catalogo():
    """O contrato com o sincronizador: turma é feminino (alterada, removida)."""
    atual = {"turma:10": ("turma", TURMA), "aluno:20": ("aluno", ALUNO)}
    assert {e.tipo for e in detectar(atual, {}).eventos} == {
        "ieducar.turma.alterada",
        "ieducar.aluno.alterado",
    }
    anterior = {"turma:10": "h", "servidor:7": "h", "aluno:20": "h"}
    assert {e.tipo for e in detectar({}, anterior).eventos} == {
        "ieducar.turma.removida",
        "ieducar.servidor.removido",
        "ieducar.aluno.removido",
    }
