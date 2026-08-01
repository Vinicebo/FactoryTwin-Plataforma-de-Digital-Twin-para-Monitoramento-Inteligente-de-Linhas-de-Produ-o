# Arquitetura técnica

Complementa o [README](../README.md) com o *porquê* das escolhas. O README mostra
como rodar; este documento explica o desenho.

## 1. Camadas do backend

```
api/v1/endpoints/   ← HTTP: validação, autorização, códigos de status
services/           ← regras de negócio (simulador, alarmes, OEE, IA)
crud/               ← acesso a dados (queries SQLAlchemy)
models/             ← ORM
schemas/            ← contratos Pydantic (entrada e saída)
```

A regra é simples: **endpoints não escrevem SQL e services não sabem o que é um
código HTTP**. Isso é o que permite o simulador — que roda fora de qualquer request
— reaproveitar `alarm_engine` e `analytics` sem adaptação.

O caso mais concreto: `compute_oee()` é chamado pelo endpoint REST, pelo evento
`line_summary` do WebSocket e pelos testes. Se a fórmula estivesse no endpoint, as
três origens poderiam divergir.

## 2. Concorrência

O simulador é uma `asyncio.Task` criada no `lifespan` da aplicação, no mesmo
processo da API.

```python
outcome = await asyncio.to_thread(self.tick)   # trabalho de banco, síncrono
await self._publish(outcome)                    # broadcast, assíncrono
```

O SQLAlchemy usado aqui é síncrono. Chamá-lo direto no event loop travaria toda a
API a cada tick, então o `tick()` inteiro vai para uma thread e só o broadcast
volta ao loop.

A cadência desconta o tempo de processamento:

```python
elapsed = loop.time() - started
await asyncio.sleep(max(0.0, self.tick_seconds - elapsed))
```

Sem isso, um tick lento empurraria todos os seguintes e a série temporal ficaria
irregular.

**Isolamento de falhas:** uma exceção no tick é registrada e o laço continua. Um
erro transitório de banco não pode matar o gêmeo digital.

## 3. O modelo do simulador

Três mecanismos dão realismo sem virar simulação física.

### Inércia térmica

Filtro de primeira ordem — a temperatura persegue o alvo em vez de saltar:

```python
state.temperature += (target - state.temperature) * THERMAL_RESPONSE  # 0.18
```

Com `THERMAL_RESPONSE = 0.18`, a injetora leva ~60 ticks (2 min) para ir de 24 °C
ao patamar de 195 °C. É o que torna o gráfico de temperatura uma curva, e não uma
sequência de degraus.

### Desgaste

Um acumulador por máquina, de 0 a 1, que sobe enquanto ela produz:

- aumenta a vibração (`vib_warning × (0.45 + 0.55 × wear)`);
- derruba a eficiência (até −18 pontos percentuais);
- multiplica a probabilidade de falha por até 5×;
- **zera na manutenção**.

Isso produz o ciclo que se espera de um equipamento real: degradação gradual →
falha → reparo → volta ao normal.

### Estrangulamento a jusante

Se a estação anterior não está `RUNNING`, a seguinte perde eficiência e, após
`STARVATION_TICKS`, entra em `IDLE` por falta de material.

É o mecanismo que gera o gradiente de OEE ao longo da linha (88% na primeira
estação, 57% na última) sem que nada no código privilegie uma máquina específica.

## 4. Motor de alarmes

O ciclo de vida é `ACTIVE → ACKNOWLEDGED → RESOLVED`, com três garantias.

**Deduplicação.** No máximo um alarme aberto por `(máquina, código)`. Sem isso, uma
temperatura alta por 10 minutos geraria 300 alarmes (um por tick).

**Escalonamento.** Se a condição piora, o alarme aberto é promovido em vez de um
novo ser criado — e um `WARNING` já reconhecido que vira `CRITICAL` volta para
`ACTIVE`, porque a situação mudou e precisa de nova atenção.

**Histerese.** A resolução exige folga de 5% além do gatilho:

```python
case AlarmCode.HIGH_TEMPERATURE:
    return reading.temperature < machine.temp_warning * (1 - DEADBAND)
```

Sem banda morta, uma grandeza oscilando em torno do limite abriria e fecharia
alarmes continuamente — o clássico *alarm flooding*, que na prática faz o operador
ignorar o painel.

Os limites vêm da tabela `machines`, não do código: adicionar um equipamento com
faixas próprias é cadastro, não desenvolvimento.

## 5. Detecção de anomalias

`Pipeline(StandardScaler → IsolationForest)`, com `contamination = 0.03`.

A decisão central é **o que entra no modelo**. Em vez de valores absolutos, as
features são razões contra o nominal de cada máquina:

| Feature | Cálculo |
|---------|---------|
| `temp_ratio` | `temperature / temp_nominal` |
| `speed_ratio` | `speed / speed_nominal` |
| `efficiency` | `efficiency / 100` |
| `energy_ratio` | `energy / energy_nominal` |
| `vibration_ratio` | `vibration / vib_warning` |
| `pressure_ratio` | `pressure / pressure_nominal` |

Com isso, "operando normalmente" é sempre ≈ 1.0, seja na injetora a 195 °C ou na
esteira a 38 °C — um único modelo cobre a linha inteira. Modelos por máquina
exigiriam histórico separado para cada uma e retreino a cada equipamento novo.

O treino usa apenas amostras em `RUNNING`: o objetivo é aprender a operação normal,
e paradas planejadas distorceriam essa noção.

**Sem o artefato, o detector fica inativo** e a plataforma segue funcionando. A
Fase 8 é um acréscimo, não uma dependência.

## 6. Tempo real

Um `ConnectionManager` global mantém o conjunto de sockets abertos. Tanto o
simulador quanto os endpoints REST publicam pelo mesmo barramento.

**Snapshot na conexão.** O primeiro evento traz máquinas, alarmes abertos e resumo
da linha. Sem ele, o painel ficaria em branco até o próximo tick.

**Depois, só deltas.** Telemetria, mudanças de estado e eventos de alarme. O
`line_summary` (que exige agregação) vai a cada 5 ticks, não a cada um.

**Cliente lento não derruba o simulador.** Todo envio é embrulhado; quem falhar é
removido do conjunto:

```python
results = await asyncio.gather(*(self._safe_send(ws, event) for ws in targets),
                               return_exceptions=True)
```

**Reconexão com backoff.** O `useRealtime` reconecta com atraso exponencial de 1 s
a 15 s. Reiniciar o backend não exige recarregar a página.

## 7. Portabilidade SQLite ↔ PostgreSQL

Três ajustes fazem o mesmo código rodar nos dois bancos:

| Situação | Solução |
|----------|---------|
| Enums | `native_enum=False` → VARCHAR + CHECK, em vez de `CREATE TYPE` |
| PK da série temporal | `BigInteger().with_variant(Integer, "sqlite")` — só `INTEGER` tem AUTOINCREMENT no SQLite |
| `ON DELETE CASCADE` | `PRAGMA foreign_keys=ON` no evento `connect` |

O terceiro item causou um bug real durante o desenvolvimento: sem o PRAGMA, apagar
uma máquina deixava alarmes órfãos e, como o SQLite reaproveita o rowid da última
linha removida, esses registros apareciam colados à próxima máquina cadastrada.

A agregação por bucket de tempo, que difere entre os dialetos, foi resolvida
gravando buckets horários em `production_records` — a consulta vira um `SUM`
portável.

## 8. Estado no frontend

Não há Redux nem React Query. O estado do dashboard é derivado de um único
`useRealtime(token)`, que aplica os eventos sobre o snapshot:

```
snapshot        → substitui máquinas, alarmes e resumo
telemetry       → atualiza os campos de leitura de cada máquina
machine_status  → troca o estado de uma máquina
alarm_raised    → insere no topo da lista
alarm_resolved  → remove da lista
```

As páginas são funções puras desse estado. `Analytics` é a exceção: OEE histórico e
status do modelo são consultas REST pontuais, não fluxo contínuo.

As ações do operador (reconhecer, resolver, comandar estado) chamam a API e **não
mexem no estado local** — a atualização chega pelo evento correspondente. Isso
evita a divergência clássica entre o otimismo do cliente e a verdade do servidor.

## 9. O que ficaria diferente em produção

| Item | Hoje | Em produção |
|------|------|-------------|
| Schema | `create_all` no boot | Migrações Alembic |
| Série temporal | Tabela relacional | TimescaleDB ou particionamento por tempo |
| Retenção | `purge_older_than` manual | Job agendado |
| Simulador | Dentro do processo da API | Serviço separado, ou CLPs reais via OPC UA/MQTT |
| Broadcast | Estado em memória | Redis Pub/Sub (permite escalar horizontalmente) |
| Token | Só access token | Refresh token e revogação |
| Segredos | `.env` | Cofre de segredos |
| Observabilidade | Logs | Métricas Prometheus e tracing |

A limitação mais relevante para escala é o `ConnectionManager` em memória: com mais
de uma réplica do backend, cada uma só alcançaria os próprios clientes. Redis
Pub/Sub entre as réplicas resolveria sem mudar o contrato do frontend.
