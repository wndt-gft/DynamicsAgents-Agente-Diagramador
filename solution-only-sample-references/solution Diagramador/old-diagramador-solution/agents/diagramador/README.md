# Diagramador – Gerador de Diagramas C4 / ArchiMate 3.0 Assistido por IA

[![Version](https://img.shields.io/badge/version-4.0-blue.svg)]() [![Python](https://img.shields.io/badge/python-3.10+-green.svg)]() [![ArchiMate](https://img.shields.io/badge/ArchiMate-3.0-orange.svg)]() [![Google ADK](https://img.shields.io/badge/Google_ADK-1.12-red.svg)]()

> Gera diagramas de arquitetura (C4 em ArchiMate 3.0) a partir de user stories em linguagem natural, aplicando metamodelo corporativo, convenções e validações automatizadas.

---
## 🔖 TL;DR
Forneça uma user story → o agente analisa → gera elementos + relacionamentos → produz XML ArchiMate válido + relatório de qualidade (naming / estrutura / documentação / compliance). Pode operar local, em pipeline ou como agente implantado no Vertex AI (ADK).

---
## 📚 Sumário
1. Visão Geral
2. Pipeline Arquitetural
3. Principais Capacidades
4. Stack & Dependências
5. Estrutura de Pastas
6. Instalação
7. Configuração / Variáveis de Ambiente
8. Uso Rápido (CLI & Web / ADK)
9. Fluxo Interno (Detalhado)
10. Componentes Principais
11. Qualidade & Métricas
12. Testes & Cobertura
13. Performance / Load
14. Deployment (GCP / Terraform / ADK)
15. Troubleshooting
16. Contribuição
17. Roadmap
18. Glossário
19. Licença / Avisos

---
## 1. Visão Geral
O agente transforma user stories em artefatos arquiteturais padronizados, reduzindo retrabalho de modelagem manual e acelerando documentação técnica governada por metamodelo.

---
## 2. Pipeline Arquitetural
```
User Story ─▶ Análise Semântica ─▶ Mapeamento ▶ Geração ▶ Validação ▶ XML + Relatório
```
Fluxo macro:
```
┌─────────────┐  ┌──────────────┐  ┌───────────────┐  ┌────────────┐  ┌──────────────┐
│ User Story  │→ │ Analyzer      │→ │ Element Mapper │→│ Generators │→│ Validators    │
└─────────────┘  └──────────────┘  └───────────────┘  └────────────┘  └──────┬───────┘
                                                                    XML + Quality Report
```

---
## 3. Principais Capacidades
- Análise semântica (LLM / fallback determinístico)
- Geração de diagramas C4 (Context / Container; extensível para Component/Code)
- Conformidade com metamodelo corporativo (XML ArchiMate)
- Validação: metamodelo + schema + regras especializadas + métricas
- Enforcers: layout de camadas, integridade XML, normalização de nomes
- Relatório de qualidade com pontuação e recomendações

---
## 4. Stack & Dependências
| Categoria | Tecnologia |
|-----------|------------|
| Linguagem | Python 3.10+ |
| LLM / Agente | Google ADK (Vertex AI) + fallback offline |
| Modelagem | ArchiMate 3.0 / C4 Model |
| Infra opcional | Terraform + GCP (Storage, Logging) |
| Testes | Pytest + cobertura integrada |
| Performance | Locust (opcional; fallback simplificado) |

---
## 5. Estrutura de Pastas (resumida)
```
agents/diagramador/
  app/
    agent.py                 # Entry do agente
    agent_engine_app.py      # App ADK / Engine (stream_query fallback)
    prompt.py                # Base de prompting
    metamodel/               # Metamodelo corporativo + validadores
    template/                # Templates SDLC / layout
    tools/
      analyzers/             # (Em evolução) extração semântica / heurísticas
      generators/            # Template / metamodel / id / compliant pipelines
      validators/            # Quality, schema, c4, naming extended
      utilities/             # xml_integrity, naming, layout, file ops, context
      diagram_service.py     # Orquestração principal
      config_manager.py      # Cache + leitura de configuração
    utils/                   # gcs / tracing / logging toggles / typing
  outputs/                   # XML gerados
  tests/                     # Suites + README de testes
  deployment/terraform       # Infra (GCP)
  test_results/              # Cobertura unificada
  logs/ (se criado externamente) # Preferir tests/logs para execução de testes
```
### Nota de Normalização de Diretórios
Se alguma pasta for criada fora do padrão (ex: `logs/` duplicado), centralize artefatos de teste em `tests/logs/` e mantenha apenas `outputs/` para resultados funcionais.

---
## 6. Instalação
### Ambiente
Requer Python ≥3.10. Recomendado uso de *virtual env* ou **uv**.
```bash
# Clonar repositório (exemplo)
cd agents/diagramador
pip install -r requirements.txt
# ou usando uv (se disponível)
uv pip sync requirements.txt
```

### Verificação rápida
```bash
python -m app.agent --help
```

---
## 7. Configuração / Variáveis de Ambiente
Crie `.env` (opcional) na raiz de `agents/diagramador`.

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| GOOGLE_CLOUD_PROJECT | Projeto GCP para logging/tracing | `my-project` |
| MODEL_AGENT_ARCHITECT | Modelo base usado pelo agente principal | `gemini-2.5-pro` |
| MODEL_AGENT_ARCHITECT_LIB | Caminho (módulo:Classe) para registrar modelos customizados | `custom.registry:MyArchitectModel` |
| MODEL_AGENT_SEARCH | Modelo utilizado pelo agente auxiliar de pesquisa | `gemini-1.5-flash` |
| MODEL_AGENT_SEARCH_LIB | Registro complementar para o modelo de pesquisa (ex.: Anthropic Claude) | `anthropic.registry:ClaudeSearchModel` |
| METAMODEL_PATH | Caminho metamodelo | `app/metamodel/metamodelo.xml` |
| DIAGRAMADOR_OUTPUT_DIR | Diretório de saída | `outputs` |
| TESTING | Ativa fallbacks determinísticos | `true` |

Fallbacks neutros são aplicados quando ausentes. Caso nenhuma variável de modelo seja informada, o agente utiliza `gemini-2.5-pro` e considera o modelo como nativo do ADK.

### 7.1 Modelos & Registro Dinâmico
O módulo `agents/model_register.py` expõe a função `configure_model`, responsável por ler variáveis de ambiente, interpretar diferentes formatos e registrar classes personalizadas no `LLMRegistry` quando necessário. Recursos suportados:

- Strings simples (ex.: `gemini-2.5-pro`), assumindo modelo nativo.
- Tokens com delimitadores (`model::pacote.modulo:Classe` ou `model|pacote.modulo:Classe`) que definem simultaneamente o identificador e a classe de registro.
- Payload JSON permitindo maior clareza:
  ```json
  {
    "model": "my-provider/model-x",
    "registry": "vendor.sdk:CustomModel"
  }
  ```

Os registries declarados são importados dinamicamente e cadastrados uma única vez (cache interno evita registros duplicados). Para forçar um registro específico independentemente da configuração de modelo, utilize as variáveis `MODEL_AGENT_ARCHITECT_LIB` ou `MODEL_AGENT_SEARCH_LIB`.

**Exemplo Anthropic Claude (agente principal + busca):**
```bash
# Exemplo de configuração do modelo para Anthropic Claude 
MODEL_AGENT_ARCHITECT=claude-opus-4-1@20250805                      # modelo real a ser usado pelo agente diagramador
MODEL_AGENT_ARCHITECT_LIB=google.adk.models.anthropic_llm:Claude    # opcional, factory customizada para Claude
MODEL_AGENT_SEARCH=claude-opus-4-1@20250805                         # modelo real a ser usado pelo agente de busca das siglas
MODEL_AGENT_SEARCH_LIB=google.adk.models.anthropic_llm:Claude       # opcional, factory customizada para Claude
```
Formato JSON equivalente: `MODEL_AGENT_SEARCH='{ "model": "anthropic/claude-opus-4-1", "registry": "google.adk.models.anthropic_llm:Claude" }'`.

---
## 8. Uso Rápido
### ADK Web
```bash
cd agents/diagramador
adk web --port 8000
```
Acesse: http://localhost:8000

### CLI direta
```bash
python app/agent.py --input "Como usuário, quero acompanhar transações via portal web"
```
Saídas em `outputs/*.xml`.

---
## 9. Fluxo Interno (Detalhado)
1. **Parsing & Normalização** – limpeza básica de texto, detecção de domínio / atores
2. **Análise** – extração de candidatos (sistemas externos, containers, integrações)
3. **Mapeamento** – geração de estrutura intermediária (elementos, relações, camadas)
4. **Geração XML** – aplicação de template + metamodelo + IDs determinísticos
5. **Enforcements** – layout, naming, integridade estrutural
6. **Validação** – schema, compliance, métricas e scoring
7. **Relatório** – agregação de métricas e recomendações

---
## 10. Componentes Principais (app/tools)
| Arquivo / Módulo | Função | Observação |
|------------------|--------|------------|
| `diagram_service.py` | Orquestra pipeline | Ponto central de composição |
| `generators/*` | Geração (template, metamodel, IDs) | Extensível | 
| `validators/*` | Métricas e compliance | Consolidado em quality + schema |
| `utilities/*` | Naming, XML integrity, layout, file ops | Reuso amplo |
| `config_manager.py` | Config consolidada | Cache leve |

### Subpastas (Detalhe)
| Subpasta | Status | Função | Observações |
|----------|--------|--------|-------------|
| analyzers | Parcial | Extração de atores / sistemas / domínios | Pode estar parcialmente desativada em cobertura incremental |
| generators | Ativo | Converte análise em XML (template / metamodel) | Dividir em etapas reduz complexidade |
| validators | Ativo | Métricas, compliance, schema, naming | Consolidar logs de falha para tuning |
| utilities | Ativo | Serviços horizontais (naming, integridade, layout) | Reuso amplo em pipelines |

---
## 11. Qualidade & Métricas
Indicadores fornecidos (exemplos):

| Métrica | Descrição | Faixa |
|---------|-----------|-------|
| `overall_score` | Score consolidado de qualidade | 0–100 |
| `naming_conventions_score` | Aderência a padrões de nome | 0–100 |
| `structure_score` | Completude estrutural / camadas | 0–100 |
| `relationships_score` | Qualidade das relações | 0–100 |
| `documentation_score` | Percentual de elementos documentados | 0–100 |
| `is_metamodel_compliant` | Conformidade metamodelo | bool |

Causas comuns de queda:
- Camadas faltantes (Channels / Execution / Data)
- Relações ausentes / inválidas
- Elementos sem descrição
- Nomes genéricos ou sem contexto funcional

---
## 12. Testes & Cobertura
Veja `tests/README.md` para detalhes (estratégia incremental, cobertura combinada). Executar pipeline completo:
```bash
python tests/run_tests.py
```
Relatórios: `tests/logs/` (logs), `test_results/coverage_html/index.html` (HTML). Threshold inicial reduzido para permitir evolução modular.

### Reconfigurando Estrutura Quebrada
Caso pastas tenham sido movidas:
1. Verifique presença de `app/tools/*` (analyzers, generators, validators, utilities)
2. Restaure `tests/README.md` para instruções de cobertura
3. Garanta `.coveragerc` na raiz (não somente dentro de tests)
4. Execute:
```bash
coverage erase
python tests/run_tests.py --suite unit
python tests/run_tests.py --suite integration --no-benchmarks
```
5. Se a cobertura cair para ~8% inesperadamente, confirme que os módulos grandes ainda constam em `omit`.

---
## 13. Performance / Load
Load test (Locust) em `tests/load_test/load_test.py` (fallback se Locust ausente). Métricas: throughput, latências p50–p99, erro e uso de recursos (psutil opcional). Relatórios em `tests/logs/`.

### Logs de Load
Todos os logs e relatórios (`load_test_report_*.txt`, `load_test_stats_*.json`) agora vão para `tests/logs/` — remover versões órfãs em raiz se existirem.

---
## 14. Deployment (GCP / Terraform / ADK)
| Artefato | Local | Função |
|----------|-------|--------|
| Terraform | `deployment/terraform` | Buckets, contas de serviço, logs |
| ADK App | `app/agent_engine_app.py` | Empacotamento + stream query |
| Metadados | `deployment_metadata.json` | Persistência após deploy |

Passos (alto nível):
1. Provisionar recursos (`terraform apply`)
2. Configurar credenciais gcloud
3. Executar script de deploy (custom) ou fluxo ADK (criação/atualização)

### Observabilidade (Logging & Tracing)
| Item | Com ADK | Fallback TESTING=true |
|------|---------|-----------------------|
| Cloud Logging | Ativado se libs + credenciais | Skippado (logs locais) |
| Tracing OTEL | Exportador configurado se disponível | No-op / silencioso |
| Feedback Stream | Event objects (author/model) | Eventos determinísticos |

---
## 15. Troubleshooting
| Sintoma | Possível Causa | Ação |
|---------|----------------|------|
| XML vazio | Falha em análise ou geração filtrada | Verificar logs `INFO` / ativar `TESTING=true` |
| Score baixo de naming | Concatenação redundante / falta de domínio | Revisar `utilities/naming_conventions.py` |
| Ausência de camadas | Story insuficiente | Enriquecer user story (atores, canais, dados) |
| Erro schema | Ordem inválida / tags faltantes | Validar pipeline / diff com exemplo válido |
| Eventos de stream vazios | Modo teste não habilitado | Exportar `TESTING=true` |
| Cobertura caiu para ~8% | `.coveragerc` ausente ou módulos re-incluídos sem testes | Restaurar omit / adicionar testes |

### Segurança / Boas Práticas
| Risco | Mitigação |
|-------|----------|
| Injeção em user story | Sanitização básica + normalização de nomes |
| XML malformado | `xml_integrity_enforcer` + validação schema |
| Vazamento de credenciais | Evitar eco de env vars em logs; usar `.env` local |
| Overwrite de outputs | Estruturar nomes com timestamp (já aplicado) |

### Limitações Conhecidas
- Cobertura parcial de módulos de análise avançada (fase incremental)
- Export apenas ArchiMate XML (outros formatos em roadmap)
- Sem versionamento de artefatos via storage remoto por default

---
## 16. Contribuição
Workflow:
1. Branch: `feature/*` ou `fix/*`
2. Implementar + testes (mínimo unit + caso negativo)
3. `python tests/run_tests.py --suite unit`
4. Ajustar cobertura se módulo reintroduzido
5. Commit (Conventional Commits)
6. PR: incluir impacto, risco, rollback

Estilo: código limpo, nomes descritivos, evitar duplicação lógica (preferir utilidades). Não introduzir dependências sem justificativa.

---
## 17. Roadmap
| Versão | Objetivos | Status |
|--------|-----------|--------|
| 4.1 | Diagramas Component (C4 L3), personalização de template | Em análise |
| 4.2 | Multi‑idioma (EN/ES), API pública REST, métricas runtime | Planejado |
| 5.0 | Export PlantUML / Draw.io, interação conversacional avançada | Futuro |

### Extensibilidade (Hooks Futuros)
| Área | Possível Hook | Benefício |
|------|---------------|-----------|
| Pré-análise | Normalizadores customizados | Adaptar a domínios específicos |
| Geração | Estratégias alternativas (PlantUML) | Multi-formato de saída |
| Validação | Regras organizacionais extras | Compliance regulatório interno |
| Qualidade | Plugins de scoring adicionais | Métricas comparativas |

---
## 18. Glossário
| Termo | Definição |
|-------|-----------|
| Metamodelo | Conjunto de regras estruturais corporativas aplicadas ao ArchiMate |
| Enforcer | Módulo que aplica automaticamente uma regra (layout, naming, integridade) |
| Compliance Score | Índice consolidado de aderência estrutural e semântica |
| C4 | Modelo de abstrações context/container/component/code |

---
## 19. Licença / Avisos
Uso interno; metamodelo pode conter informações proprietárias. Revisar restrições antes de distribuição externa.

### Disclaimer Adicional
Este projeto contém lógica orientada a metamodelo interno; revise direitos antes de expor endpoints externamente.

---
**Status Atual:** Base estabilizada; foco agora em ampliar cobertura real, introduzir Component Diagram e evoluir recomendações de arquitetura.

> Para aprofundar em qualidade e cobertura consulte `tests/README.md`.
