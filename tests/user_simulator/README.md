# Simulador de usuário para o agente Diagramador

Este diretório reúne um cenário de teste manual pensado para ser executado contra o agente Diagramador usando o Google ADK e o modelo configurado via variáveis de ambiente. O objetivo é permitir uma validação ponta a ponta – com a LLM real – registrando cada evento, estado de sessão e artefato gerado.

## Estrutura geral

```
/tests/user_simulator/
  run_user_simulation.py        # Script principal da simulação
  README.md                     # Este documento
  test-cases/
    pix_container/
      Agent_diagramador_prompt.txt    # Prompt completo do agente utilizado
      flow.json                        # Definição do fluxo da simulação
      user_history.txt                 # História de usuário que será enviada
      session.log                      # Log consolidado da última execução (gerado pelo script)
      artefacts/                       # Pasta onde os artefatos exportados serão armazenados
      results/                         # Pasta com execuções anteriores (cada uma em um subdiretório)
```

Durante a execução, o script cria uma nova pasta em `results/` contendo:

- `session.log`: todos os eventos emitidos pelo ADK em formato JSON Lines.
- `flow_result.json`: resumo do fluxo executado com checkpoints relevantes.
- `artefacts/`: cópias dos arquivos gerados pelos tools (PNG, SVG, XML, JSON, etc.).
- `NNN-Agent-Tool-Interaction_session_state.json`: snapshots do estado de sessão após cada interação.
- `structured_summary.md`: detalhamento final e sugestões retornadas pela LLM.

## Pré-requisitos

1. Python 3.12+
2. Dependências instaladas do projeto (`pip install -r requirements.txt`).
3. Pacotes oficiais `google-adk` e `google-genai` instalados no mesmo ambiente (`pip install -r tests/user_simulator/requirements.txt`).
4. Variáveis de ambiente necessárias para autenticação e seleção de modelo, por exemplo:
   - `GOOGLE_APPLICATION_CREDENTIALS`
   - `GOOGLE_CLOUD_PROJECT`
   - `DIAGRAMADOR_MODEL` (opcional, padrão `gemini-2.5-pro`)

## Executando a simulação

```bash
python tests/user_simulator/run_user_simulation.py --case pix_container
```

Parâmetros disponíveis:

- `--case`: identificador do caso em `tests/user_simulator/test-cases/` (padrão: `pix_container`).
- `--dry-run`: gera apenas os arquivos de configuração sem disparar a LLM (útil para validar instalação).
- `--run-name`: nome customizado para a execução (caso queira algo diferente do timestamp padrão).

## Fluxo da simulação

1. Carrega a história de usuário e o fluxo definido em `flow.json`.
2. Instancia o `InMemoryRunner` do Google ADK com o agente Diagramador.
3. Cria uma sessão em memória e envia as mensagens do fluxo.
4. Para cada evento retornado:
   - Registra em `session.log` (JSON Lines).
   - Captura o estado de sessão completo, salvando com o padrão `NNN-Agent-Tool-Interaction_session_state.json`.
   - Baixa os artefatos disponibilizados pelos tools para a pasta `artefacts/`.
5. Ao final, salva `flow_result.json` com metadados e `structured_summary.md` contendo o detalhamento estruturado pedido à LLM.

## Observações importantes

- O script não mascara as credenciais; execute-o apenas em ambiente seguro.
- A simulação depende da disponibilidade do modelo escolhido no Google GenAI.
- Se o ADK sinalizar necessidade de confirmação de ferramentas ou autenticação adicional, os registros aparecerão em `session.log` para análise manual.
- É possível adicionar novos cenários criando subpastas em `test-cases/` seguindo o mesmo padrão de arquivos.
