# Architect Agent ADK – Test Suite

> Unified automation for quality: smoke → unit → integration → (optional) load + coverage + reporting.

---
## 📚 Table of Contents
1. Overview
2. Directory Layout
3. Environment & Dependency Setup
4. Quick Start (90% of what you need)
5. Command Reference
6. Coverage Strategy (Incremental Improvement)
7. Re‑introducing Omitted Modules Checklist
8. Running with Pytest Directly
9. Load / Performance Testing
10. Environment & Modes
11. Markers & Test Taxonomy
12. Test Design Guidelines
13. Troubleshooting Guide
14. CI Integration Snippet
15. Roadmap / Next Steps
16. Deep Dive por Arquivo de Teste

---
## 1. Overview
The test harness consolidates all QA entry points into a single orchestrator (`run_tests.py`). It standardizes logging, environment bootstrapping, deterministic fallbacks (via `TESTING=true`), and coverage consolidation.

---
## 2. Directory Layout
| Path | Purpose |
|------|---------|
| `run_tests.py` | Orchestrator script (smoke/unit/integration/load) |
| `unit/` | Fine‑grained logic verification |
| `integration/` | Cross‑module flows, streaming, feedback, concurrency |
| `load_test/` | Locust (or fallback) performance harness |
| `logs/` | Central sink: all suite + load test logs & reports |
| `test_results/` | Coverage (HTML/XML/JSON) + aggregated execution report |
| `.coveragerc` | Incremental coverage policy (omit + thresholds) |
| `conftest.py` | Global fixtures, markers, async event loop, mocks |

---
## 3. Environment & Dependency Setup
Todos os comandos assumem que você está na raiz do repositório (`architect-ai-copilot`). Ajuste os caminhos conforme necessário se estiver em outro diretório.

```bash
# (Opcional) criar virtualenv dedicado
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Instalar dependências mínimas para executar as suites
pip install -r agents/diagramador/tests/requirements.txt
```

> 💡 O arquivo de requisitos lista dependências “core” (ADK, PyArchiMate, pytest) e utilidades opcionais (mkdocs, locust, plugins de lint). Instale somente o necessário: o runner identifica bibliotecas ausentes e alterna para *fallbacks* seguros sempre que possível.【F:agents/diagramador/tests/requirements.txt†L1-L55】

Para provisionar um ambiente isolado de carga com Locust (sem poluir sua virtualenv principal), **entre primeiro em `agents/diagramador/tests/`** e então execute `load_test/setup_load_tests.sh`. O script depende do diretório de trabalho atual para gerar arquivos (`load_test/run_load_test.sh`, `load_test/.results/`, etc.) e irá falhar se rodado a partir da raiz do repositório. Uma sequência válida seria:

```bash
cd agents/diagramador/tests
./load_test/setup_load_tests.sh
```

O script cria `.venv_load_test`, instala versões certificadas de Locust/psutil/requests, gera `run_load_test.sh` e `requirements.txt` específicos e prepara `agents/diagramador/tests/load_test/.results` para relatórios HTML/CSV automatizados.【F:agents/diagramador/tests/load_test/setup_load_tests.sh†L1-L137】

## 4. Quick Start
```bash
# Full pipeline (smoke + unit + integration + load fallback)
python agents/diagramador/tests/run_tests.py

# Only unit
python agents/diagramador/tests/run_tests.py --suite unit

# Unit + verbose details
python agents/diagramador/tests/run_tests.py --suite unit --verbose

# Integration only
python agents/diagramador/tests/run_tests.py --suite integration

# Skip load stage
python agents/diagramador/tests/run_tests.py --no-benchmarks

# Custom load (if Locust installed)
python agents/diagramador/tests/run_tests.py --suite load --load-duration 60 --load-users 10
```
**Artifacts:** after execution inspect `agents/diagramador/tests/logs/` (logs) and `agents/diagramador/tests/test_results/coverage_html/index.html` (coverage UI).

---
## 5. Command Reference (Cheat Sheet)
| Goal | Command |
|------|---------|
| Full suite | `python agents/diagramador/tests/run_tests.py` |
| Smoke only | `python agents/diagramador/tests/run_tests.py --suite smoke` |
| Unit + integration (no load) | `python agents/diagramador/tests/run_tests.py --no-benchmarks` |
| Load only (30s / 5 users default) | `python agents/diagramador/tests/run_tests.py --suite load` |
| Extended load | `python agents/diagramador/tests/run_tests.py --suite load --load-duration 120 --load-users 25 --spawn-rate 5` |
| Force verbose | `python agents/diagramador/tests/run_tests.py --suite unit --verbose` |
| Raw pytest unit (coverage) | `pytest agents/diagramador/tests/unit --cov=app --cov-config=agents/diagramador/.coveragerc` |
| Append integration coverage | `pytest agents/diagramador/tests/integration --cov=app --cov-config=agents/diagramador/.coveragerc --cov-append` |
| Single test debug | `pytest agents/diagramador/tests/unit/test_generators.py::TestGenericDiagramGenerator::test_generate_context_diagram -vv -s` |

---
## 6. Coverage Strategy (Incremental Improvement)
Massive modules are *temporarily excluded* to prevent denominator inflation while focused tests are authored. See `.coveragerc` `omit` entries:
```
*/app/tools/analyzers/*
*/app/tools/diagram_service.py
*/app/tools/generators/*
*/app/tools/validators/*
*/app/tools/utilities/template_layout_enforcer.py
*/app/tools/utilities/xml_integrity_enforcer.py
```
**Current threshold:** `fail_under = 35` (raise only when stable & green). 

### Recommended Elevation Path
| Phase | Action | Target | Exit Criteria |
|-------|--------|--------|---------------|
| 1 | Keep omissions | ≥35% | Stable green builds |
| 2 | Re‑include utilities (context/file/naming) | ≥45% | Added unit tests for utilities |
| 3 | Re‑include a single generator module | ≥55% | Core generation paths covered |
| 4 | Re‑include validators | ≥65% | Error + success paths validated |
| 5 | Re‑include diagram_service | ≥75% | End‑to‑end flows tested |
| 6 | Re‑include analyzers (final) | ≥80% | Domain extraction scenarios covered |

### Minimal Coverage Sanity Cycle
```bash
coverage erase
pytest agents/diagramador/tests/unit --cov=app --cov-config=agents/diagramador/.coveragerc
pytest agents/diagramador/tests/integration --cov=app --cov-config=agents/diagramador/.coveragerc --cov-append
coverage html -d agents/diagramador/tests/test_results/coverage_html
```

---
## 7. Re‑introducing Omitted Modules Checklist
1. Remove module pattern from `.coveragerc` `omit`.
2. Add targeted unit tests (positive + failure + boundary case).
3. Add at least one integration scenario if cross‑component.
4. Re-run combined coverage (commands above).
5. Ensure no explosive test runtime; refactor large fixture reuse if needed.
6. Commit with message: `test: add coverage for <module> (raise threshold if applicable)`.

---
## 8. Running with Pytest Directly
```bash
# Fast loop (single file)
pytest agents/diagramador/tests/unit/test_message_processor.py -q

# Focused marker filtering
pytest -m "unit and not slow" -q
pytest -m integration -q

# Fail fast on first 3 failures
pytest agents/diagramador/tests/unit -x --maxfail=3
```
Add `--lf` (last failed) or `--ff` (failed first) to accelerate iterative fixes.

---
## 9. Load / Performance Testing
If **Locust** is present, full scenario classes run (standard, stress, endurance, spike, resilience). Otherwise a **fallback** executes a simplified synthetic loop (never fails pipeline). 

Artifacts (always) → `agents/diagramador/tests/logs/`:
- `load_test_*.log`
- `load_test_report_*.txt`
- `load_test_stats_*.json`

Quick headless example:
```bash
locust -f agents/diagramador/tests/load_test/load_test.py --headless -t 90s -u 15 -r 3
```

> 📌 Executar `agents/diagramador/tests/load_test/setup_load_tests.sh` cria um ambiente isolado para carga, gera `run_load_test.sh` com parâmetros reutilizáveis (`duracao`, `usuarios`, `spawn_rate`, `host`) e preenche `agents/diagramador/tests/load_test/.results` com relatórios HTML/CSV prontos para anexar no pipeline de QA.【F:agents/diagramador/tests/load_test/setup_load_tests.sh†L25-L125】

---
## 10. Environment & Modes
| Variable | Effect | Typical Dev |
|----------|--------|-------------|
| `TESTING` | Enables deterministic stream + skips cloud logging & tracing | `true` |
| `GOOGLE_CLOUD_PROJECT` | Cloud logging / tracing project id | `test-project` |
| `GOOGLE_CLOUD_LOCATION` | Region for cloud resources | `us-central1` |
| `MODEL_AGENT_ARCHITECT` | Overrides architect agent base model (see below) | `gemini-2.5-pro` |
| `MODEL_AGENT_ARCHITECT_LIB` | Forces registry import for architect model | `vendor.registry:ArchitectModel` |
| `MODEL_AGENT_SEARCH` | Overrides search assistant model | `gemini-1.5-flash` |
| `MODEL_AGENT_SEARCH_LIB` | Forces registry import for search model (ex.: Anthropic Claude) | `anthropic.registry:ClaudeSearchModel` |

> ℹ️ A resolução de modelos é feita por `agents/model_register.configure_model`, aceitando valores simples (`gemini-2.5-pro`), tokens com delimitadores (`model::pacote.modulo:Classe`) ou JSON. Se uma lib for informada (`*_LIB`), ela é registrada no `LLMRegistry` antes da execução dos testes. Para provedores externos (ex.: Anthropic Claude), utilize o pacote de variáveis abaixo:
> ```bash
> # Exemplo de configuração do modelo para Anthropic Claude
> MODEL_AGENT_ARCHITECT=claude-opus-4-1@20250805                      # modelo real a ser usado pelo agente diagramador
> MODEL_AGENT_ARCHITECT_LIB=google.adk.models.anthropic_llm:Claude    # opcional, factory customizada para Claude
> MODEL_AGENT_SEARCH=claude-opus-4-1@20250805                         # modelo real a ser usado pelo agente de busca das siglas
> MODEL_AGENT_SEARCH_LIB=google.adk.models.anthropic_llm:Claude       # opcional, factory customizada para Claude
> ```

PowerShell example:
```powershell
$env:TESTING="true"
```

---
## 11. Markers & Test Taxonomy
| Marker | Purpose |
|--------|---------|
| `smoke` | Environment + import sanity |
| `unit` | Isolated functional logic |
| `integration` | Multi‑module flow / side effects |
| `slow` | Long‑running scenario (>~5s) |
| `load` | Performance / Locust harness |

Combine markers: `pytest -m "unit and not slow"`.

---
## 12. Test Design Guidelines
**Principles**:
- Deterministic (no external network, no time flakiness – mock or freeze time if needed)
- AAA pattern (Arrange / Act / Assert) – avoid multiple asserts of unrelated concerns per test
- Boundaries first: min / empty / malformed / large payload
- Explicit naming: `test_<function>_<condition>_<expected>()`
- Avoid over‑mocking: prefer testing real code paths until boundaries reach external edges

**Patterns to Cover**:
| Category | Examples |
|----------|----------|
| Normal flow | Nominal successful generation / validation |
| Failure | Invalid types, malformed XML, missing fields |
| Edge | Empty story, special chars, large payload, unicode |
| Concurrency | Parallel generation / analysis (thread/async) |
| Security | Input sanitization / injection attempt rejection |

---
## 13. Troubleshooting Guide
| Symptom | Cause | Resolution |
|---------|-------|------------|
| Coverage collapsed to ~8% | Omitted modules reintroduced or integration not appended | Re-run two‑phase coverage + confirm `.coveragerc` exists |
| No streaming events | Not in TESTING mode & backend fallback path unused | Set `TESTING=true` or inspect `stream_query` fallback |
| Unit stage very slow | Huge modules re‑included prematurely | Re‑omit or split tests; add targeted subsets |
| Load logs missing | Older `load_test.py` version | Ensure central logging patch applied |
| Marker not recognized | Marker not registered in `conftest.py` | Verify `pytest_configure` markers |

---
## 14. CI Integration Snippet
```yaml
- name: Run Test Pipeline
  run: python agents/diagramador/tests/run_tests.py --suite all --no-benchmarks

- name: Upload Coverage HTML
  uses: actions/upload-artifact@v4
  with:
    name: coverage-html
    path: agents/diagramador/tests/test_results/coverage_html

- name: Upload Coverage XML (Codecov)
  uses: codecov/codecov-action@v4
  with:
    files: agents/diagramador/tests/test_results/coverage.xml
    fail_ci_if_error: true
```

---
## 15. Roadmap / Next Steps
| Goal | Action |
|------|--------|
| Raise baseline coverage to 50% | Re‑include utilities + author tests |
| Stabilize integration speed | Profile slow tests, cache heavy fixtures |
| Strengthen validation | Add property tests (naming, XML integrity) |
| Observability | Add timing/size metrics fixture + log aggregation |
| Flake detection | Integrate rerun plugin or custom flake tracker |

---
**Need a starting point?** Pick one omitted module, write 3 focused tests: (happy path, invalid input, boundary). Re‑enable it in coverage and iterate.

---
## 16. Deep Dive por Arquivo de Teste

Este capítulo descreve todas as suites presentes em `agents/diagramador/tests/` com o contexto necessário para QA, manutenção e expansão. Cada entrada detalha a motivação do arquivo, cenários cobertos, dependências/fallbacks e como aproveitar o material em investigações futuras.

### 16.1 Infraestrutura compartilhada
- **`agents/diagramador/tests/run_tests.py`** — Orquestrador com correções de encoding para Windows, enumeração das suites (`all`, `unit`, `integration`, `load`, `smoke`, `performance`), dataclasses de resultado/cobertura e pipeline que força o diretório raiz, prepara logging em `agents/diagramador/tests/logs/`, valida ferramentas (`python`, `pytest`, `coverage`) e executa comandos sempre em UTF-8, inclusive ajustando `GEVENT_NOWAITPID` para subprocessos gevent/locust.【F:agents/diagramador/tests/run_tests.py†L1-L189】
- **`agents/diagramador/tests/conftest.py`** — Define *stubs* para bibliotecas opcionais (`dotenv`, Google ADK/GenAI), disponibiliza classes mínimas de agentes/respostas/eventos, prepara caminhos, e injeta fixtures reusáveis (loops assíncronos, diretórios temporários, mock de LLM, contexto do agente, etc.) garantindo determinismo em ambientes sem SDK oficial.【F:agents/diagramador/tests/conftest.py†L1-L200】

### 16.2 Unidade – Núcleo do agente e callbacks
- **`agents/diagramador/tests/unit/test_agent_core.py`** — Valida `get_agent_capabilities`, o fluxo principal de `process_message` com normalização Unicode/logging, `diagram_generator_tool` em cenários feliz/erro e `quality_validator_tool` tanto no caminho metamodelo quanto fallback, além da utilidade privada `_decode_unicode_escapes`。【F:agents/diagramador/tests/unit/test_agent_core.py†L1-L109】
- **`agents/diagramador/tests/unit/test_additional_coverage.py`** — Cobertura suplementar para alternância de logging por variável de ambiente, tratamento de exceções em `process_message`, concatenação de `steps`/`etapas` na geração de diagramas e fallback resiliente do validador de qualidade quando a construção do serviço falha.【F:agents/diagramador/tests/unit/test_additional_coverage.py†L1-L101】
- **`agents/diagramador/tests/unit/test_agent_engine_app_core.py`** — Exercita `AgentEngineApp` em modo `TESTING`, cobrindo *health check*, feedback válido/inválido, métricas acumuladas, isolamento de estado e `stream_query` assíncrono com contador de requisições.【F:agents/diagramador/tests/unit/test_agent_engine_app_core.py†L1-L88】
- **`agents/diagramador/tests/unit/test_callback_postprocessing.py`** — Garante que os *callbacks* pós-processamento sanitizam URLs GCS em strings/dicionários, extraem/validam links, corrigem variantes `gs://`/HTTPS e preservam estado em `CallbackContext` antes de entregar respostas para o ADK.【F:agents/diagramador/tests/unit/test_callback_postprocessing.py†L1-L104】

### 16.3 Unidade – Serviços de confirmação, mensagem e sessão
- **`agents/diagramador/tests/unit/test_confirmation_handler.py`** — Mapeia a máquina de estados de confirmação: confirmações positivas/negativas, respostas ambíguas que pedem esclarecimento, prevenção de reprocessamento após `mark_diagram_generated` e tratamento de entrada nula.【F:agents/diagramador/tests/unit/test_confirmation_handler.py†L1-L56】
- **`agents/diagramador/tests/unit/test_message_processor.py`** — Abrange detecção de user stories PT/EN, contagem de mensagens processadas, reset de estado, resposta para mensagens vazias ou de ajuda/saudação e extração de tipo de diagrama solicitado (context/container/component/all).【F:agents/diagramador/tests/unit/test_message_processor.py†L1-L200】

### 16.4 Unidade – Serviços de diagrama
- **`agents/diagramador/tests/unit/test_diagram_service_mapped.py`** — Avalia `DiagramService.process_mapped_elements` com sucessos mínimos, validações de elementos/relacionamentos, remoção de `BusinessActor`, regras de camada (Gateway inbound), ignorância de IDs desconhecidos e falha do validador de schema quando ativado.【F:agents/diagramador/tests/unit/test_diagram_service_mapped.py†L1-L149】
- **`agents/diagramador/tests/unit/test_diagram_service_user_story.py`** — Exercita `process_user_story` tanto no modo metamodelo (geração, layout, resumo de camadas, relatório de qualidade) quanto no fallback determinístico que produz XML sintético e relatórios simples.【F:agents/diagramador/tests/unit/test_diagram_service_user_story.py†L1-L72】

### 16.5 Unidade – Geração e qualidade de diagramas
- **`agents/diagramador/tests/unit/test_generators.py`** — Conjunto extenso que mocka geradores genéricos, baseados em template e metamodelo: prepara histórias de múltiplos domínios, valida limites (história vazia/longa), template inválido, IDs determinísticos, integridade XML e desempenho dos geradores.【F:agents/diagramador/tests/unit/test_generators.py†L1-L200】
- **`agents/diagramador/tests/unit/test_c4_quality_extended.py`** — Exercita `C4QualityValidator` com metamodelo real ou mocks, cobrindo inicialização, validação completa, análise de métricas (estrutura, naming, relacionamentos, documentação, conformidade), tratamento de XML inválido e geração de relatórios de qualidade.【F:agents/diagramador/tests/unit/test_c4_quality_extended.py†L1-L120】
- **`agents/diagramador/tests/unit/test_schema_validator.py`** — Smoke de `ArchiMate30SchemaValidator` validando XMLs válidos/inválidos, *batch validate*, checagem de tipos permitidos, geração de relatórios estruturados e regras customizadas com severidades distintas.【F:agents/diagramador/tests/unit/test_schema_validator.py†L1-L171】
- **`agents/diagramador/tests/unit/test_xml_integrity.py`** — Cobertura completa do `XMLIntegrityEnforcer`: valida/ajusta arquivos, corrige problemas de referência, reforça sanitarização contra `script`/`javascript`, gera relatórios com severidade e acompanha issues/warnings simulados.【F:agents/diagramador/tests/unit/test_xml_integrity.py†L1-L200】
- **`agents/diagramador/tests/unit/test_naming_conventions.py`** — Testa o aplicador de convenções para componentes, deduplicação por tecnologia, melhorias automáticas, relatório de conformidade e helpers C4 para containers, atores e rótulos de relacionamentos.【F:agents/diagramador/tests/unit/test_naming_conventions.py†L1-L66】

### 16.6 Unidade – Utilitários de arquivos, contexto e download
- **`agents/diagramador/tests/unit/test_file_context_handler.py`** — Cobre `OutputManager` (salvar diagramas, análises, user stories, criar diretórios, listar arquivos), formatação de sumários/relatórios e gerenciamento de contexto via `AgentContext` e `get_agent_context`.【F:agents/diagramador/tests/unit/test_file_context_handler.py†L1-L200】
- **`agents/diagramador/tests/unit/test_utilities.py`** — Bateria ampla validando integridade XML, naming, geração de IDs, persistência de arquivos, contexto do agente, processamento de mensagens, enforcer de layout e demais utilitários exportados em `app.tools.utilities` com mocks equivalentes quando necessário.【F:agents/diagramador/tests/unit/test_utilities.py†L1-L200】
- **`agents/diagramador/tests/unit/test_local_download.py`** — Exercita criação de links locais, fallback para `gs://local_files` quando o upload GCS falha, escrita de arquivos ausentes, fluxos de erro e mensagens amigáveis para indisponibilidade crítica.【F:agents/diagramador/tests/unit/test_local_download.py†L1-L96】

### 16.7 Unidade – Configuração e inicialização
- **`agents/diagramador/tests/unit/test_config_manager.py`** — Suite orientada a `ConfigManager`: inicialização, descoberta do diretório padrão, carregamento/merge de múltiplos YAMLs, tolerância a arquivos ausentes/invalidos, idempotência, busca com *defaults*, reset de singleton e acesso a `get_config`/`get_config_manager`.【F:agents/diagramador/tests/unit/test_config_manager.py†L1-L200】
- **`agents/diagramador/tests/unit/test_config_init.py`** — Garante que `app.config` reexporta `Settings`, `get_settings`, `ANALYSIS_PROMPTS` e `BANKING_PATTERNS`, além de popular `__all__` adequadamente via *stubs* injetados.【F:agents/diagramador/tests/unit/test_config_init.py†L1-L30】
- **`agents/diagramador/tests/unit/test_init_module.py`** — Audita `__init__` de `app`, `app.tools`, subpacotes (`generators`, `validators`, `utilities`) e verifica que exports/fallbacks permanecem chamáveis mesmo quando importações específicas falham.【F:agents/diagramador/tests/unit/test_init_module.py†L1-L200】
- **`agents/diagramador/tests/unit/test_tools_init_fallback.py`** — Recarrega `app.tools`/`app.tools.utilities` forçando caminhos de fallback, garantindo que funções como `validate_diagram_quality`, `analyze_user_story`, `generate_container_diagram` e helpers de contexto estejam disponíveis.【F:agents/diagramador/tests/unit/test_tools_init_fallback.py†L1-L37】
- **`agents/diagramador/tests/unit/test_smoke.py`** — Sanidade estrutural do projeto: presença de diretórios/arquivos chaves, importabilidade de módulos principais, instanciabilidade de geradores/validadores/utilities e pequenas asserções de linguagem Python para detectar ambientes problemáticos.【F:agents/diagramador/tests/unit/test_smoke.py†L1-L200】

### 16.8 Unidade – Pesquisa, analisadores e toggles
- **`agents/diagramador/tests/unit/test_discovery_engine_search.py`** — Exercita a ferramenta de busca Discovery Engine em três modos: dependências ausentes, configuração incompleta e execução completa com clientes fake; também garante ordenação por similaridade e filtragem por *threshold*.【F:agents/diagramador/tests/unit/test_discovery_engine_search.py†L1-L165】
- **`agents/diagramador/tests/unit/test_analyzers.py`** — Conjunto rico para `UnifiedStoryAnalyzer` e funções `analyze_user_story*`, com mocks de API, geração/limpeza de análise inteligente, detecção de domínio/sistema/atores, extração de sistemas externos e criação de containers/componentes a partir da análise semântica.【F:agents/diagramador/tests/unit/test_analyzers.py†L1-L120】

### 16.9 Unidade – Qualidade adicional e fallback utilitário
- **`agents/diagramador/tests/unit/test_confirmation_handler.py`** (já descrito acima) e **`agents/diagramador/tests/unit/test_local_download.py`** fornecem coberturas críticas para evitar regressões nos fluxos de confirmação e entrega de artefatos.
- **`agents/diagramador/tests/unit/test_additional_coverage.py`** (seção 16.2) reforça caminhos excepcionais do agente; combine sua leitura com `test_agent_core` ao investigar problemas de logging ou de merges de passos.

### 16.10 Integração ponta-a-ponta
- **`agents/diagramador/tests/integration/test_agent_engine_app.py`** — Substitui dependências ADK reais e valida `AgentEngineApp`: `stream_query` assíncrono, métricas ao vivo, feedback com média ponderada, `get_agent_capabilities` e fluxo de `set_up` em cenários reais vs. mocks.【F:agents/diagramador/tests/integration/test_agent_engine_app.py†L1-L200】
- **`agents/diagramador/tests/integration/test_agent_integration.py`** — Modelo de integração completo que define `UserStory`, `C4Diagram`, agentes/serviços mockados (LLM, PlantUML, validação), testa geração unitária e em lote, streaming de estágios, cache, exportação para arquivo e relatórios de validação agregados.【F:agents/diagramador/tests/integration/test_agent_integration.py†L1-L200】
- **`agents/diagramador/tests/integration/test_c4_service_integration.py`** — Similar ao anterior porém focado no serviço C4: prompts específicos por tipo (context/container/component/code), lote de histórias, renderização PlantUML em múltiplos formatos e verificação de conteúdo UML gerado.【F:agents/diagramador/tests/integration/test_c4_service_integration.py†L1-L200】

### 16.11 Performance e carga
- **`agents/diagramador/tests/load_test/load_test.py`** — Suite empresarial com suporte a Locust ou fallback determinístico: monitora CPU/memória/disco via `psutil`, organiza cenários (stress/endurance/spike), gera relatórios em `agents/diagramador/tests/logs/`, normaliza logging UTF-8 e define *decorators* compatíveis quando Locust não está instalado.【F:agents/diagramador/tests/load_test/load_test.py†L1-L200】
- **`agents/diagramador/tests/load_test/README.md`** complementa com instruções dedicadas de setup Locust/psutil e execução headless; consulte-o antes de acoplar o runner a pipelines de performance.【F:agents/diagramador/tests/load_test/README.md†L1-L37】

> 💡 **Dica de QA:** ao depurar uma regressão, combine o arquivo unitário correspondente com a seção de integração correlata. Por exemplo, falhas de naming devem ser vistas em `test_naming_conventions.py`, `test_utilities.py` (validador cruzado) e, se envolver relatórios de qualidade, em `test_c4_quality_extended.py`.
