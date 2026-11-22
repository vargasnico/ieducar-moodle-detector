"""Monta o estado de cada turma, servidor e aluno a partir dos dados lidos do i-Educar.
Função pura: é esse estado (completo) que vai em cada evento, para que quem consome
não precise consultar o i-Educar."""

from collections import defaultdict

from detector.dominio.modelos import DadosDoAno

# Estado do ano: chave ("turma:10") → (tipo, dados).
Estado = dict[str, tuple[str, dict]]


def series_com_componentes(d: DadosDoAno) -> set[tuple[int, int]]:
    """Pares (escola, série) cujos componentes precisam ser lidos: os das turmas ativas
    e os das enturmações ativas."""
    pares = {(t.escola_id, s) for t in d.turmas if t.ativo for s in t.series}
    matriculas = {m.matricula_id: m for m in d.matriculas if m.ativo}
    for e in d.enturmacoes:
        if e.ativa and (m := matriculas.get(e.matricula_id)):
            pares.add((m.escola_id, e.serie_id))
    return pares


def montar_estado(d: DadosDoAno) -> Estado:
    estado: Estado = {}

    def componentes(escola_id: int, serie_id: int) -> list[dict]:
        return [
            {"id": c.componente_id, "nome": c.nome} for c in d.componentes[(escola_id, serie_id)]
        ]

    # Turmas, com os componentes das suas séries (curso = turma × componente).
    for t in d.turmas:
        comps: dict[int, str] = {}
        if t.ativo:
            for serie_id in t.series:
                for c in componentes(t.escola_id, serie_id):
                    comps.setdefault(c["id"], c["nome"])
        estado[f"turma:{t.turma_id}"] = (
            "turma",
            {
                "turma_id": t.turma_id,
                "nome": t.nome,
                "ano": d.ano,
                "ativa": t.ativo,
                "componentes": [{"id": i, "nome": n} for i, n in sorted(comps.items())],
            },
        )

    # Servidores, com os vínculos ativos (turma e componentes) do ano.
    vinculos: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
    for v in d.vinculos:
        if v.ativo:
            vinculos[v.servidor_id][v.turma_id].update(v.componentes)
    for s in d.servidores:
        estado[f"servidor:{s.servidor_id}"] = (
            "servidor",
            {
                "servidor_id": s.servidor_id,
                "nome": s.nome,
                "cpf": "".join(ch for ch in s.cpf or "" if ch.isdigit()) or None,
                "email": s.email,
                "ativo": s.ativo,
                "vinculos": [
                    {"turma_id": turma_id, "componentes": sorted(c)}
                    for turma_id, c in sorted(vinculos[s.servidor_id].items())
                ],
            },
        )

    # Alunos, com as turmas em que estão e os componentes que cursam em cada uma
    # (os da série, menos os de dispensa).
    alunos = {a.aluno_id: a for a in d.alunos}
    matriculas = {m.matricula_id: m for m in d.matriculas if m.ativo and m.aluno_id in alunos}
    dispensas: dict[int, set[int]] = defaultdict(set)
    for disp in d.dispensas:
        if disp.ativa:
            dispensas[disp.matricula_id].add(disp.componente_id)
    turmas_do_aluno: dict[int, list[dict]] = defaultdict(list)
    for e in d.enturmacoes:
        m = matriculas.get(e.matricula_id)
        if e.ativa and m:
            da_serie = {c["id"] for c in componentes(m.escola_id, e.serie_id)}
            turmas_do_aluno[m.aluno_id].append(
                {
                    "turma_id": e.turma_id,
                    "componentes": sorted(da_serie - dispensas[m.matricula_id]),
                }
            )
    for a in alunos.values():
        estado[f"aluno:{a.aluno_id}"] = (
            "aluno",
            {
                "aluno_id": a.aluno_id,
                "nome": a.nome_social or a.nome,
                "ativo": a.ativo,
                "turmas": sorted(turmas_do_aluno[a.aluno_id], key=lambda x: x["turma_id"]),
            },
        )
    return estado
