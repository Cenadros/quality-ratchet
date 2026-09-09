# Quality Ratchet — KPI de calidad de código monotónico

Fecha: 2026-09-08
Estado: diseño aprobado en chat, pendiente de plan de implementación

## Objetivo

Disponer de un KPI cuantificable de calidad de código que se pueda monitorizar tras cada sesión de trabajo (con IA o sin ella) y que **nunca empeore**: cada PR se compara contra una línea base commiteada y el merge solo es posible si ninguna métrica retrocede. La línea base solo se mueve hacia mejor (ratchet).

Requisito duro: reutilizable en cualquier proyecto y lenguaje. Turnify (Swift + Kotlin + TypeScript) es el primer consumidor, no el único.

## Contexto de partida (Turnify, verificado 2026-09-08)

- 99k LOC: Swift 48.850, Kotlin 42.508, TypeScript 5.317, Ruby 1.170, Shell 701.
- 131 archivos de test, ~1.126 funciones de test (579 `@Test` Android, 547 `func test` iOS).
- CI (`.github/workflows/*.yml`): cuatro workflows, todos de release. **Ninguno ejecuta tests ni lint.**
- Cobertura: ninguna herramienta en ninguna plataforma.
- Linters: solo swiftlint (`ios/Turnify/.swiftlint.yml`, dos reglas de tamaño). Android sin linter.
- Hooks git: ninguno.

Consecuencia: la v1 se construye con métricas que **no requieren ejecutar tests**. La cobertura queda para una v2 cuando CI ejecute las suites.

## Alternativas descartadas

- **Ratchet de cobertura como único KPI**: recolección por lenguaje, fácil de inflar, iOS bajo Xcode 27 beta crashea suites en `main`. Entra en v2 como métrica más, no como KPI único.
- **SonarCloud / SonarQube**: llave en mano pero dependencia de proveedor, Swift solo en planes de pago, no corre en local tras una sesión.
- **Solo métricas estructurales sin score**: cumple el gate pero no da el número único que se pide monitorizar.

## Decisiones

| Decisión | Valor |
|---|---|
| Dónde vive | Repo propio `Cenadros/quality-ratchet`: CLI + GitHub Action + README |
| Lenguaje del CLI | Python, un paquete pequeño, sin dependencias salvo los colectores |
| Puntos de corte | CI en PR (required check) **y** hook local `Stop` de Claude Code (aviso) |
| Métricas v1 | complejidad (lizard), duplicación (jscpd), warnings de linters, ratio tests/código |
| KPI único | Quality Score 0-100 derivado de las métricas; informa, no corta |
| Qué corta | Cada métrica individual contra su baseline, con tolerancia |
| Política de baseline | Solo mejora; aflojar exige `--force --reason "<motivo>"` |

## Arquitectura

### Ficheros en el repo consumidor

`quality-ratchet.yml` (config):

```yaml
version: 1
include: [ios, android, firebase/functions/src]
exclude: [build, node_modules, .build, Pods, fastlane, docs, "*.generated.*"]
tests:
  dirs: ["**/src/test/**", "**/src/androidTest/**", "**/*Tests/**", "**/*UITests/**"]
  patterns:
    kt: "@Test"
    swift: "func test"
    ts: "\\b(it|test)\\("
thresholds:
  ccn: 15
  function_nloc: 60
duplication:
  min_tokens: 50
linters:
  swiftlint: { cwd: ios/Turnify }
score:
  weights: { complexity: 0.30, duplication: 0.25, lint: 0.25, tests: 0.20 }
tool_versions:
  lizard: "1.17.x"
  jscpd: "4.x"
  scc: "3.x"
```

`quality-baseline.json` (estado, commiteado):

```json
{
  "version": 1,
  "commit": "e482e10",
  "tool_versions": { "lizard": "1.17.10", "jscpd": "4.0.5", "scc": "3.4.0", "swiftlint": "0.57.0" },
  "initial": { "ccn_over_15": 42, "max_ccn": 38, "long_functions": 17, "duplication_pct": 3.1, "lint_warnings": 120, "tests_per_kloc": 11.4 },
  "metrics": {
    "ccn_over_15":     { "value": 42,   "better": "lower" },
    "max_ccn":         { "value": 38,   "better": "lower" },
    "long_functions":  { "value": 17,   "better": "lower" },
    "duplication_pct": { "value": 3.1,  "better": "lower",  "tolerance": 0.1 },
    "lint_warnings":   { "value": 120,  "better": "lower" },
    "tests_per_kloc":  { "value": 11.4, "better": "higher", "tolerance": 0.2 }
  },
  "score": 50
}
```

Los valores numéricos de arriba son ilustrativos; la baseline real se genera en `main` en el paso 2 del despliegue. `initial` congela los valores del primer cálculo y sirve de referencia para normalizar el score.

### Colectores

Contrato: cada colector es una función `collect(config, root) -> dict[str, float]`. Detecta su herramienta al arrancar. Si falta, `check` falla con mensaje explícito (`lizard not found: pip install lizard`). Nunca omite una métrica en silencio: una métrica ausente hace la baseline no comparable.

| Métrica | Herramienta | Detalle |
|---|---|---|
| `ccn_over_15` | `lizard --csv` | número de funciones con CCN > `thresholds.ccn` |
| `max_ccn` | `lizard --csv` | CCN máximo del proyecto |
| `long_functions` | `lizard --csv` | funciones con NLOC > `thresholds.function_nloc` |
| `duplication_pct` | `jscpd --reporters json` | % de líneas duplicadas; ignora dirs de test y generados |
| `lint_warnings` | linters con config presente | swiftlint `--reporter json`; detekt, ktlint, eslint, ruff cuando exista su config; suma total de warnings + errors |
| `tests_per_kloc` | grep de `tests.patterns` + `scc --format json` | funciones de test por cada 1.000 LOC de producción (LOC total menos `tests.dirs`) |

Excludes por defecto (sin config): `build/`, `node_modules/`, `.build/`, `Pods/`, `*.generated.*`, `fastlane/`, `docs/`.

### Quality Score

Score 0-100, media ponderada de cuatro componentes normalizados contra `initial`. La baseline inicial ancla el score en 50: hay recorrido en ambas direcciones y reducir una métrica a cero la lleva a 100.

- Métrica `lower`: `componente = clamp(1 - value / (2 * initial), 0, 1)`. En `initial` vale 0,5; en 0 vale 1; al doblar `initial` vale 0. Si `initial` es 0, el componente se queda neutral (0,5) mientras `value` siga en 0 y cae a 0,0 en cuanto suba — un repo sin warnings de partida no se lleva puntos gratis por no tenerlos.
- Métrica `higher`: `componente = clamp(value / (2 * initial), 0, 1)`. En `initial` vale 0,5; al doblar vale 1. Si `initial` es 0, el componente vale 1,0 en cuanto `value` sea mayor que 0 (cualquier test vence a ninguno) y se queda neutral (0,5) mientras siga en 0.
- Componente complejidad = media de las tres métricas de lizard; los otros tres componentes tienen una métrica cada uno.
- `score = round(100 * Σ peso_i * componente_i)`.

Propiedad exigida: el score no sube si alguna métrica empeora más que su tolerancia. Se garantiza porque el gate corta antes por métrica; el score es informe, no gate.

La baseline guarda además un hash corto de `quality-ratchet.yml` (`config_hash`): un cambio en la config es un evento de re-anchor igual que un bump de versión de herramienta, y `update` lo exige explícito con `--force --reason`.

### Comandos

- `quality-ratchet check [--github]`: calcula, compara con baseline, imprime tabla de deltas, exit 1 si alguna métrica empeora más que su tolerancia. Con `--github` emite annotations y un job summary.
- `quality-ratchet update [--force --reason "<motivo>"]`: reescribe la baseline solo con valores mejores. Sin `--force`, un valor peor se ignora y se avisa. Con `--force` exige `--reason` y lo guarda en `history[]` dentro del JSON.
- `quality-ratchet report`: tabla + score, exit 0 siempre. Para el hook local.
- `quality-ratchet init`: genera `quality-ratchet.yml` con defaults detectados por extensión y la baseline inicial.

Salida de `check`:

```
metric            baseline   now   delta   status
ccn_over_15             42    44      +2   FAIL
duplication_pct        3.1   3.0    -0.1   ok  ↑
score                   50    49      -1   FAIL
```

### Determinismo

Mismo commit debe producir los mismos números. Versiones de colectores pineadas en `tool_versions` de la config; la baseline guarda las versiones con las que se calculó. `check` avisa (no falla) si las versiones difieren: cambiar de versión de lizard mueve números sin que cambie el código. Tras un cambio de versión se regenera la baseline con `update --force --reason "bump lizard 1.17→1.18"`.

### Errores

| Situación | Comportamiento |
|---|---|
| Baseline ausente | `check` la crea, imprime "baseline inicial, nada que comparar", exit 0 |
| Métrica nueva en config sin valor en baseline | se añade con el valor actual, no falla |
| Métrica en baseline sin colector en config | falla: config rota |
| Herramienta de un colector ausente | falla con instrucción de instalación |
| Config ausente | usa defaults por extensión y avisa |

### Puntos de corte

1. **GitHub Action en PR** (`.github/workflows/quality.yml` del consumidor): `check --github` contra la baseline de la rama base. Required check en branch protection tras dos PRs verdes.
2. **Push a `main`**: `update`; si la baseline cambia, commit `chore(quality): baseline ↑ score 52→54` (mismo patrón que `roadmap-sync.yml`). Ese commit no toca versión y no dispara `release-train.yml`.
3. **Hook `Stop` de Claude Code** en `.claude/settings.json` del consumidor: `quality-ratchet report`. Aviso en terminal, no bloqueo.
4. **`/finish`**: ejecuta `check` como parte del gate de calidad.

## Tests del propio ratchet

pytest sobre un repo fixture mínimo (tres ficheros Swift/Kotlin/TS con una función de CCN 20, una función de 80 NLOC, un bloque duplicado y dos tests):

- cada colector devuelve los valores esperados del fixture;
- `check` falla al empeorar, pasa al mejorar, respeta la tolerancia en el límite exacto;
- `update` nunca afloja sin `--force --reason`; con `--force` registra el motivo;
- score sube al mejorar una métrica y baja al empeorarla;
- baseline ausente crea baseline y exit 0;
- herramienta ausente falla con el mensaje de instalación.

## Despliegue en Turnify

1. Repo `Cenadros/quality-ratchet` v0.1.0: CLI, Action (`uses: Cenadros/quality-ratchet@v0`), README con quickstart.
2. Turnify: `quality-ratchet.yml` + baseline inicial generada en `main`. PR con etiquetas `semver:patch` y `skip-release-notes`.
3. `.github/workflows/quality.yml`: PR → `check --github`; push a `main` → `update` + commit.
4. Hook `Stop` en `.claude/settings.json` de Turnify con `quality-ratchet report`; `/finish` invoca `check`.
5. Required check en branch protection de `main`, tras dos PRs verdes.

## Fuera de alcance v1

- Cobertura (v2, cuando CI ejecute tests en ambas plataformas).
- detekt / Android lint para Android: hoy Android no tiene linter, `lint_warnings` arranca solo con swiftlint. Issue aparte.
- Badge de score en README.
- Histórico del score por commit (dashboard). Se puede reconstruir desde los commits `chore(quality)`.
