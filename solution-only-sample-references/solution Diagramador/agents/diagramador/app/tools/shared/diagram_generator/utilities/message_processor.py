"""
Message Processing Module
Handles user message analysis and classification
"""

import logging
from typing import Optional, Any, Dict
import re

logger = logging.getLogger(__name__)


def is_user_story(message: str) -> bool:
    """
    Verifica se a mensagem é uma user story

    Args:
        message: Mensagem do usuário

    Returns:
        bool: True se é uma user story, False caso contrário
    """
    if not message:
        return False
    message_lower = message.lower()

    # Palavras‑sinal (incluem espaço à direita para evitar coincidências parciais)
    user_story_patterns = [
        "como ",  # role (pt)
        "quero ",  # action (pt)
        "para ",  # benefit (pt)
        "desejo ",  # synonym (pt)
        "preciso ",  # synonym (pt)
        "want ",  # action (en)
        "need ",  # action (en)
        "would like ",  # polite action (en)
        "so that ",  # benefit (en)
        "as a ",  # role (en)
        "as an "  # role (en with an)
    ]

    pattern_count = sum(1 for pattern in user_story_patterns if pattern in message_lower)

    # Regex específicos mais abrangentes (ordenados por idioma)
    specific_patterns = [
        # Português: Como <ator>[,] (quero|desejo|preciso) ... para ...
        r"como[^\n]*?(quero|desejo|preciso)[^\n]*?para",
        # Inglês: As a/an <role>, I (want|need|would like) ... (so that ...)?
        r"as a[n]?\s+[^,]+,?\s+i\s+(want|need|would like)[^\n]*?(so that)?",
        # Formatos abreviados multiline (Português)
        r"como[\s\S]*?(quero|desejo|preciso)",
    ]

    for pattern in specific_patterns:
        if re.search(pattern, message_lower):
            return True

    # Critério geral
    return pattern_count >= 2 and len(message_lower.split()) >= 5


def extract_diagram_type_from_message(message: str) -> Optional[str]:
    """
    Extrai o tipo de diagrama especificado na mensagem do usuário.

    Args:
        message: Mensagem do usuário

    Returns:
        Optional[str]: Tipo de diagrama detectado ou None
    """
    message_lower = message.lower()

    # Padrões aprimorados para detectar tipo de diagrama na mensagem
    patterns = {
        'context': [
            'gerar diagrama: context', 'diagrama: context', 'context diagram', 'diagrama de contexto', 'contexto',
            'gerar contexto', 'quero o diagrama de contexto', 'faça o diagrama de contexto', 'crie o diagrama de contexto',
            'gere o diagrama de contexto', 'tipo: context', 'context', 'c1'
        ],
        'container': [
            'gerar diagrama: container', 'diagrama: container', 'container diagram', 'diagrama de container',
            'diagrama container', 'containers', 'gerar container', 'quero o diagrama de container',
            'faça o diagrama de container', 'crie o diagrama de container', 'gere o diagrama de container',
            'tipo: container', 'container', 'c2'
        ],
        'component': [
            'gerar diagrama: component', 'diagrama: component', 'component diagram', 'diagrama de component',
            'diagrama component', 'componentes', 'gerar component', 'quero o diagrama de component',
            'faça o diagrama de component', 'crie o diagrama de component', 'gere o diagrama de component',
            'tipo: component', 'component', 'c3'
        ],
        'todos': [
            'gerar diagrama: todos', 'diagrama: todos', 'todos os diagramas', 'all diagrams', 'gerar todos',
            'quero todos os diagramas', 'faça todos os diagramas', 'crie todos os diagramas', 'gere todos os diagramas',
            'tipo: todos', 'todos', 'all'
        ]
    }

    # Verificar cada padrão com prioridade para padrões mais específicos primeiro
    for diagram_type, type_patterns in patterns.items():
        for pattern in type_patterns:
            if pattern in message_lower:
                logger.info(f"🎯 Detectado tipo de diagrama '{diagram_type}' no padrão: '{pattern}'")
                return diagram_type

    # Verificar padrões mais flexíveis se não encontrou padrões específicos
    # Buscar palavras-chave isoladas no final da mensagem
    words = message_lower.split()
    if words:
        last_word = words[-1].strip('.,!?')
        if last_word in ['context', 'contexto', 'c1']:
            logger.info(f"🎯 Detectado tipo 'context' na última palavra: '{last_word}'")
            return 'context'
        if last_word in ['container', 'containers', 'c2']:
            logger.info(f"🎯 Detectado tipo 'container' na última palavra: '{last_word}'")
            return 'container'
        if last_word in ['component', 'componentes', 'c3']:
            logger.info(f"🎯 Detectado tipo 'component' na última palavra: '{last_word}'")
            return 'component'
        if last_word in ['todos', 'all']:
            logger.info(f"🎯 Detectado tipo 'todos' na última palavra: '{last_word}'")
            return 'todos'

    return None


def handle_non_story_message(message: str) -> str:
    """
    Processa mensagens que não são user stories

    Args:
        message: Mensagem do usuário

    Returns:
        str: Resposta apropriada
    """
    if message is None:
        return """
Não identifiquei uma user story na sua mensagem. 

📝 Lembre-se de usar o formato:
"Como [ator], eu quero [ação] para [benefício]"

💡 Digite 'ajuda' para mais informações.
"""
    message_lower = message.lower().strip()

    help_keywords = ["ajuda", "help", "como usar", "instruções", "instrucoes", "?" ]
    if any(kw in message_lower for kw in help_keywords):
        return get_help_message()

    greeting_keywords = ["oi", "olá", "ola", "hello", "hi", "bom dia"]
    if any(kw in message_lower for kw in greeting_keywords):
        return get_welcome_message()

    return """
Não identifiquei uma user story na sua mensagem. 

📝 Lembre-se de usar o formato:
"Como [ator], eu quero [ação] para [benefício]"

💡 Digite 'ajuda' para mais informações.
"""


def get_welcome_message() -> str:
    """Retorna mensagem de boas-vindas"""
    return """
👋 **Olá! Eu sou o Architect Agent!**

🎯 **Minha especialidade:**
Transformo user stories em diagramas de arquitetura C4 usando ArchiMate.

📝 **Como usar:**
1. Envie uma user story no formato:
   "Como [ator], eu quero [ação] para [benefício]"

2. Escolha o tipo de diagrama desejado

3. Receba os arquivos XML (ArchiMate) e PlantUML

🚀 **Exemplo rápido:**
"Como cliente do banco, eu quero fazer transferências PIX para enviar dinheiro instantaneamente"

💡 Digite 'ajuda' para mais informações ou envie sua user story!
"""


def get_help_message() -> str:
    """Retorna mensagem de ajuda"""
    return """
📚 **Guia de Uso do Architect Agent**

### 📝 Formato da User Story:
```
Como [ator/papel], 
eu quero [funcionalidade/ação]
para [objetivo/benefício]
```

### 🎯 Exemplos de User Stories:
1. **Transferência PIX:**
   "Como cliente, eu quero fazer transferências via PIX para enviar dinheiro instantaneamente"

2. **Consulta de Saldo:**
   "Como correntista, eu quero consultar meu saldo para controlar minhas finanças"

3. **Pagamento de Boletos:**
   "Como usuário do app, eu quero pagar boletos para quitar minhas contas"

### 🎨 Tipos de Diagramas:
- **context**: Sistema e suas integrações externas
- **container**: Containers, apps e bancos de dados
- **component**: Componentes internos detalhados

### 💡 Dicas:
- Seja específico sobre atores e ações
- Mencione integrações importantes
- Indique requisitos de segurança
- Especifique o tipo de diagrama desejado

### 🚀 Recursos Avançados:
- Geração automática usando PyArchiMate
- Exportação em múltiplos formatos
- Análise inteligente de domínio bancário
- Conformidade com ArchiMate 3.1

Digite sua user story para começar! 
"""


# ---------------------------------------------------------------------------
# New implementations to satisfy tests and improve coverage
# ---------------------------------------------------------------------------

class MessageProcessor:
    """Stateful message processor used in tests.

    Maintains a count of processed messages and classifies input.
    Lightweight and thread-safe for simple use (increment only)."""
    __slots__ = ("processed_count",)

    def __init__(self) -> None:
        self.processed_count: int = 0

    def process(self, message: Any) -> Dict[str, Any]:
        """Process a single message returning classification metadata.

        Handles None and non-string inputs gracefully.
        """
        if message is None:
            return {"processed": False, "error": "Invalid message"}
        # Normalize to str (tests pass numbers / objects)
        if not isinstance(message, str):
            message = str(message)
        self.processed_count += 1
        cleaned = message.strip()
        story_flag = is_user_story(cleaned) if cleaned else False
        diagram_type = extract_diagram_type_from_message(cleaned) if cleaned else None
        result: Dict[str, Any] = {
            "processed": True,
            "content": message,
            "is_user_story": story_flag,
            "diagram_type": diagram_type,
            "type": "user_story" if story_flag else "message"
        }
        # Help detection (mirrors test expectations)
        if cleaned.lower() in {"ajuda", "help"}:
            result["type"] = "help"
        return result

    def reset(self) -> None:
        """Reset internal counters (used in tests)."""
        self.processed_count = 0


def process_user_message(message: Any) -> Dict[str, Any]:
    """Convenience functional wrapper used by tests.

    Returns a dict similar to MessageProcessor.process output without maintaining state.
    """
    processor = MessageProcessor()
    return processor.process(message)

__all__ = [
    "MessageProcessor",
    "process_user_message",
    "is_user_story",
    "extract_diagram_type_from_message",
    "handle_non_story_message",
    "get_help_message",
    "get_welcome_message",
]
