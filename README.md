# ieducar-moodle-detector

Microsserviço da integração i-Educar → Moodle que **descobre o que mudou no
i-Educar**. A cada ciclo (60s ou `POST /ciclos`) ele lê o ano letivo, calcula um hash
do estado de cada turma, servidor e aluno, compara com o último publicado (snapshot)
e publica um evento para cada um que mudou.

É o único serviço que fala com o i-Educar. Faz parte da integração montada em
[ieducar-moodle-integration](https://github.com/vargasnico/ieducar-moodle-integration),
que sobe tudo com um `docker compose up`.

## Contrato

**Consome:** nada (lê a API do i-Educar).

**Publica** na exchange `integracao` (topic):

| Routing key | `dados` |
|---|---|
| `ieducar.turma.alterada.v1` | `turma_id`, `nome`, `ano`, `ativa`, `componentes: [{id, nome}]` |
| `ieducar.servidor.alterado.v1` | `servidor_id`, `nome`, `cpf`, `email`, `ativo`, `vinculos: [{turma_id, componentes}]` |
| `ieducar.aluno.alterado.v1` | `aluno_id`, `nome`, `ativo`, `turmas: [{turma_id, componentes}]` |
| `ieducar.{turma,servidor,aluno}.removido.v1` | `<tipo>_id` |

Formato das mensagens em [`src/detector/mensagem.py`](src/detector/mensagem.py).
Catálogo completo no repositório de orquestração.

**Dados próprios:** `snapshot` (SQLite em `DATABASE_PATH`).

## API

| Rota | Descrição |
|---|---|
| `POST /ciclos?completo=false` | Roda um ciclo agora; `completo=true` publica todas as entidades |
| `GET /health` | 200 se conectado ao RabbitMQ |
| `GET /metrics` | `detector_ciclos_total`, `detector_eventos_total`, `detector_ciclo_segundos` |

## Resiliência

- Timeout de 3s para conectar e 10s para responder; 3 tentativas com backoff
  exponencial (tenacity) em cada consulta.
- Se o i-Educar estiver fora, o ciclo falha **sem publicar nada**.
- Publica antes de gravar o snapshot: uma queda no meio faz o próximo ciclo publicar
  de novo (os consumidores são idempotentes), e nada se perde.

## Configuração

| Variável | Padrão | Descrição |
|---|---|---|
| `RABBITMQ_URL` | `amqp://guest:guest@localhost/` | Broker |
| `DATABASE_PATH` | `data/detector.db` | Banco do serviço |
| `IEDUCAR_URL` | `http://localhost` | i-Educar |
| `IEDUCAR_ACCESS_KEY` | — | Chave da API do i-Educar |
| `IEDUCAR_INSTITUICAO_ID` | `1` | Instituição |
| `IEDUCAR_ESCOLA_ID`, `IEDUCAR_ANO_LETIVO` | — | Sem valor: escolas ativas e ano em andamento |
| `INTERVALO_SEGUNDOS` | `60` | Intervalo entre ciclos |

## Desenvolvimento

```bash
uv sync
uv run pytest
mkdir -p data && RABBITMQ_URL=amqp://integracao:integracao@localhost:5672/ \
  IEDUCAR_ACCESS_KEY=ieducar-access-key PYTHONPATH=src uv run uvicorn detector.main:app --port 8001
```

## Deploy

Cada tag `v*` roda o [CI](.github/workflows/ci.yml): testes e a imagem
`ghcr.io/<dono>/ieducar-moodle-detector:<tag>`. Para subir uma versão nova só deste
serviço no ambiente: `docker compose up -d --build detector` (ou troque a tag da
imagem), sem mexer nos outros.
