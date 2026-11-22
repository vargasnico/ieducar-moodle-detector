"""Dados do i-Educar que a integração usa, independentes de como a API os entrega."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Escola:
    escola_id: int
    nome: str
    ativo: bool


@dataclass(frozen=True)
class Servidor:
    servidor_id: int
    nome: str
    cpf: str | None
    ativo: bool
    updated_at: str
    email: str | None = None


@dataclass(frozen=True)
class Vinculo:
    """Alocação de um servidor como professor numa turma (modules.professor_turma)."""

    vinculo_id: int
    servidor_id: int
    turma_id: int
    componentes: tuple[int, ...]
    ativo: bool


@dataclass(frozen=True)
class Turma:
    turma_id: int
    nome: str
    ano: int
    escola_id: int
    # Uma turma multisseriada tem mais de uma série.
    series: tuple[int, ...]
    ativo: bool


@dataclass(frozen=True)
class Componente:
    componente_id: int
    nome: str


@dataclass(frozen=True)
class Aluno:
    aluno_id: int
    nome: str
    nome_social: str | None
    ativo: bool


@dataclass(frozen=True)
class Matricula:
    matricula_id: int
    aluno_id: int
    escola_id: int
    ativo: bool


@dataclass(frozen=True)
class Enturmacao:
    matricula_id: int
    turma_id: int
    serie_id: int
    # Sem exclusão e sem data de saída. Transferência, remanejamento, abandono e
    # falecimento mantêm deleted_at vazio e só preenchem a data de saída.
    ativa: bool


@dataclass(frozen=True)
class Dispensa:
    matricula_id: int
    componente_id: int
    ativa: bool


@dataclass
class DadosDoAno:
    """Tudo o que o detector lê do i-Educar num ciclo."""

    ano: int
    turmas: list[Turma]
    servidores: list[Servidor]  # com o e-mail (detalhe de cada um)
    vinculos: list[Vinculo]
    alunos: list[Aluno]
    matriculas: list[Matricula]
    enturmacoes: list[Enturmacao]
    dispensas: list[Dispensa]
    # Componentes que a escola oferece em cada série: (escola_id, serie_id) → lista.
    componentes: dict[tuple[int, int], list[Componente]] = field(default_factory=dict)
