# Fase 1 — Planejamento do Domínio Industrial

Este documento define o *escopo físico* que o Digital Twin representa. Todo o modelo
de dados, o simulador e as regras de alarme derivam daqui.

## 1. A linha de produção

Modelamos uma **linha de montagem e acabamento de peças plásticas injetadas**
(`LINE-01 — Montagem e Acabamento`), operando em 3 turnos.

O fluxo é sequencial: cada máquina consome a saída da anterior. Uma parada na
máquina *n* estrangula as máquinas *n+1* em diante — comportamento que o simulador
reproduz.

| # | Código | Máquina | Função | Métrica dominante |
|---|--------|---------|--------|-------------------|
| 1 | `INJ-01` | Injetora | Injeta o polímero no molde | Temperatura / Pressão |
| 2 | `CNV-01` | Esteira transportadora | Transporte entre estações | Velocidade |
| 3 | `ROB-01` | Braço robótico | Pega-e-posiciona | Vibração |
| 4 | `PNT-01` | Cabine de pintura | Aplicação de tinta | Pressão |
| 5 | `OVN-01` | Forno de cura | Cura térmica da tinta | Temperatura |
| 6 | `INS-01` | Estação de inspeção | Visão computacional / refugo | Qualidade |
| 7 | `PKG-01` | Empacotadora | Embalagem primária | Velocidade |
| 8 | `PAL-01` | Paletizadora | Paletização | Energia |

### Posição no mapa da fábrica

Cada máquina tem coordenadas `(pos_x, pos_y)` num plano normalizado `0–100`,
consumidas pelo mapa da fábrica no dashboard.

```
  y
100 ┤
    │
 60 ┤  [INJ-01]──[CNV-01]──[ROB-01]──[PNT-01]
    │                                    │
 30 ┤  [PAL-01]──[PKG-01]──[INS-01]──[OVN-01]
    │
  0 └──────────────────────────────────────── x
      10      30      50      70      90
```

## 2. Estados da máquina

Máquina de estados finita, usada tanto pelo simulador quanto pelo cálculo de OEE.

| Estado | Significado | Conta como disponível? |
|--------|-------------|------------------------|
| `RUNNING` | Produzindo normalmente | Sim |
| `IDLE` | Ligada, sem material / aguardando | Não |
| `SETUP` | Troca de ferramenta / ajuste | Não |
| `MAINTENANCE` | Manutenção planejada | Não |
| `FAULT` | Falha — parada não planejada | Não |
| `OFFLINE` | Desligada / fora do turno | Não |

Transições possíveis:

```
OFFLINE ──▶ IDLE ──▶ SETUP ──▶ RUNNING ──▶ IDLE
                                  │
                                  ├──▶ FAULT ──▶ MAINTENANCE ──▶ IDLE
                                  └──▶ MAINTENANCE
```

## 3. Sensores e grandezas medidas

Cada máquina publica uma leitura consolidada por ciclo de simulação (padrão: 2 s).
Todas as grandezas ficam na tabela `sensor_readings`.

| Grandeza | Campo | Unidade | Faixa nominal (varia por máquina) |
|----------|-------|---------|-----------------------------------|
| Temperatura | `temperature` | °C | 40 – 220 |
| Velocidade | `speed` | rpm ou m/min | 10 – 1500 |
| Eficiência | `efficiency` | % | 0 – 100 |
| Consumo de energia | `energy` | kW | 1 – 90 |
| Vibração | `vibration` | mm/s RMS | 0 – 12 |
| Pressão | `pressure` | bar | 0 – 200 |

Os limites *por máquina* (nominal, aviso, crítico) ficam na própria tabela
`machines` — assim o motor de alarmes não tem regras hard-coded por equipamento.

## 4. Indicadores (KPIs)

### Produção
- **Peças boas** (`good_count`) e **refugo** (`scrap_count`), agregados por hora em
  `production_records`.
- **Taxa de refugo** = `scrap / (good + scrap)`.

### OEE — Overall Equipment Effectiveness

```
OEE = Disponibilidade × Performance × Qualidade

Disponibilidade = tempo_produzindo / tempo_planejado
Performance     = (peças_totais × tempo_ciclo_ideal) / tempo_produzindo
Qualidade       = peças_boas / peças_totais
```

Referência de classe mundial: OEE ≥ 85%.

### Confiabilidade
- **MTBF** (Mean Time Between Failures) = tempo produzindo / nº de falhas.
- **MTTR** (Mean Time To Repair) = tempo em `FAULT` + `MAINTENANCE` / nº de falhas.

### Energia
- Consumo acumulado (kWh) e **energia por peça** (kWh/peça) — indicador de
  eficiência energética.

## 5. Regras de alarme (detalhadas na Fase 7)

| Código | Condição | Severidade |
|--------|----------|------------|
| `HIGH_TEMPERATURE` | `temperature > temp_critical` | CRITICAL |
| `HIGH_TEMPERATURE` | `temperature > temp_warning` | WARNING |
| `LOW_EFFICIENCY` | `efficiency < eff_critical` | CRITICAL |
| `LOW_EFFICIENCY` | `efficiency < eff_warning` | WARNING |
| `OVERSPEED` | `speed > speed_max` | WARNING |
| `UNDERSPEED` | `speed < speed_min` e estado `RUNNING` | WARNING |
| `HIGH_VIBRATION` | `vibration > vib_critical` | CRITICAL |
| `MACHINE_FAULT` | estado entrou em `FAULT` | CRITICAL |
| `ANOMALY_DETECTED` | modelo de ML sinaliza outlier | WARNING |

Alarmes têm ciclo de vida: `ACTIVE → ACKNOWLEDGED → RESOLVED`, com deduplicação
(um alarme ativo por `(machine, code)` de cada vez).

## 6. Perfis de usuário (detalhado na Fase 9)

| Perfil | Pode ver | Pode operar | Pode administrar |
|--------|----------|-------------|------------------|
| `VIEWER` (Visitante) | ✔ | ✘ | ✘ |
| `OPERATOR` (Operador) | ✔ | ✔ (reconhecer alarmes, mudar estado) | ✘ |
| `ADMIN` (Administrador) | ✔ | ✔ | ✔ (CRUD de máquinas e usuários) |
