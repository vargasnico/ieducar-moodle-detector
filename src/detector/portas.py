"""Portas: o que o caso de uso precisa do mundo externo, sem saber como é feito.

Os adaptadores (adaptadores/ieducar.py, adaptadores/sqlite.py, adaptadores/rabbitmq.py)
as implementam; os testes usam versões em memória.
"""

from typing import Protocol

from detector.dominio.modelos import (
    Aluno,
    Componente,
    Dispensa,
    Enturmacao,
    Escola,
    Matricula,
    Servidor,
    Turma,
    Vinculo,
)
from detector.mensagem import Mensagem


class IEducar(Protocol):
    """Leitura do i-Educar (fonte da verdade)."""

    async def listar_escolas(self) -> list[Escola]: ...
    async def ano_letivo_em_andamento(self, escola_id: int) -> int | None: ...
    async def listar_turmas(self, ano: int, escolas: list[int]) -> list[Turma]: ...
    async def listar_componentes(
        self, escola_id: int, serie_id: int, ano: int
    ) -> list[Componente]: ...
    async def listar_servidores(self) -> list[Servidor]: ...
    async def obter_servidor(self, servidor_id: int) -> Servidor | None: ...
    async def listar_vinculos(self, ano: int, escolas: list[int]) -> list[Vinculo]: ...
    async def listar_alunos(self, ano: int, escolas: list[int]) -> list[Aluno]: ...
    async def listar_matriculas(self, ano: int, escolas: list[int]) -> list[Matricula]: ...
    async def listar_enturmacoes(self, ano: int, escolas: list[int]) -> list[Enturmacao]: ...
    async def listar_dispensas(self, escolas: list[int]) -> list[Dispensa]: ...


class Snapshot(Protocol):
    """Hash do último estado publicado de cada entidade."""

    def hashes(self) -> dict[str, str]: ...
    def gravar(self, mudancas: dict[str, tuple[str, str | None]]) -> None: ...


class PublicadorDeEventos(Protocol):
    async def publicar(self, mensagem: Mensagem) -> None: ...
