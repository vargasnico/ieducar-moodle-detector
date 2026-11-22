"""Métricas do detector (Prometheus), expostas em /metrics."""

from prometheus_client import Counter, Histogram

# Usada pelo broker.py ao consumir (o detector só publica, então fica zerada).
MENSAGENS = Counter("mensagens_total", "Mensagens consumidas, por resultado", ["tipo", "resultado"])
CICLOS = Counter("detector_ciclos_total", "Ciclos de detecção, por resultado", ["resultado"])
EVENTOS = Counter("detector_eventos_total", "Mudanças detectadas no i-Educar", ["tipo"])
DURACAO_CICLO = Histogram("detector_ciclo_segundos", "Duração da leitura do i-Educar")
