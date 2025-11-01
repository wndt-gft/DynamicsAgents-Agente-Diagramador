"""
Naming Conventions - Convenções de Nomenclatura
Utilitário compartilhado para aplicação de convenções de nomenclatura em diagramas C4
Versão consolidada seguindo princípios SRP
"""

import logging
import re
from typing import Dict, List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class ElementNamingPattern(Enum):
    """Padrões de nomenclatura para diferentes tipos de elementos"""
    APPLICATION_COMPONENT = "ApplicationComponent"
    APPLICATION_SERVICE = "ApplicationService"
    BUSINESS_ACTOR = "BusinessActor"
    DATA_OBJECT = "DataObject"
    API_GATEWAY = "APIGateway"
    DATABASE = "Database"


class NamingConventionApplier:
    """Aplicador de convenções de nomenclatura para elementos de diagrama"""

    def __init__(self):
        self.naming_patterns = {
            ElementNamingPattern.APPLICATION_COMPONENT: {
                "suffix": "Service",
                "prefix": "",
                "style": "PascalCase",
                "keywords": ["service", "app", "application", "component"]
            },
            ElementNamingPattern.APPLICATION_SERVICE: {
                "suffix": "API",
                "prefix": "",
                "style": "PascalCase",
                "keywords": ["api", "service", "interface"]
            },
            ElementNamingPattern.BUSINESS_ACTOR: {
                "suffix": "",
                "prefix": "",
                "style": "Title Case",
                "keywords": ["user", "actor", "person", "role"]
            },
            ElementNamingPattern.DATA_OBJECT: {
                "suffix": "Database",
                "prefix": "",
                "style": "PascalCase",
                "keywords": ["db", "database", "storage", "data"]
            },
            ElementNamingPattern.API_GATEWAY: {
                "suffix": "Gateway",
                "prefix": "",
                "style": "PascalCase",
                "keywords": ["gateway", "proxy", "load balancer"]
            }
        }

        self.technology_mappings = {
            "spring": "Spring Boot",
            "react": "React",
            "angular": "Angular",
            "vue": "Vue.js",
            "node": "Node.js",
            "python": "Python",
            "java": "Java",
            "dotnet": ".NET",
            "postgres": "PostgreSQL",
            "mysql": "MySQL",
            "mongo": "MongoDB",
            "redis": "Redis",
            "kafka": "Apache Kafka",
            "rabbitmq": "RabbitMQ"
        }

    def apply_naming_conventions(self, element_name: str, element_type: str,
                                technology: Optional[str] = None) -> str:
        """
        Aplica convenções de nomenclatura a um elemento

        Args:
            element_name: Nome atual do elemento
            element_type: Tipo do elemento ArchiMate
            technology: Tecnologia utilizada (opcional)

        Returns:
            str: Nome melhorado seguindo convenções
        """
        try:
            # Normalizar entrada
            clean_name = self._clean_element_name(element_name)

            # Determinar padrão baseado no tipo
            pattern = self._get_naming_pattern(element_type)

            # Aplicar padrão
            improved_name = self._apply_pattern(clean_name, pattern, technology)

            # Validar resultado
            if not improved_name or improved_name == element_name:
                return element_name

            logger.info(f"📝 Nome melhorado: '{element_name}' → '{improved_name}'")
            return improved_name

        except Exception as e:
            logger.warning(f"⚠️ Erro ao aplicar convenção de nomenclatura: {e}")
            return element_name

    def _clean_element_name(self, name: str) -> str:
        """Remove caracteres inválidos e normaliza o nome"""
        if not name:
            return "Elemento"

        # Remove caracteres especiais excessivos
        cleaned = re.sub(r'[^\w\s\-_]', '', name)

        # Remove espaços múltiplos
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Se ficou vazio, usa nome padrão
        if not cleaned:
            return "Elemento"

        return cleaned

    def _get_naming_pattern(self, element_type: str) -> Dict:
        """Determina o padrão de nomenclatura baseado no tipo do elemento"""
        type_mapping = {
            "ApplicationComponent": ElementNamingPattern.APPLICATION_COMPONENT,
            "ApplicationService": ElementNamingPattern.APPLICATION_SERVICE,
            "BusinessActor": ElementNamingPattern.BUSINESS_ACTOR,
            "BusinessRole": ElementNamingPattern.BUSINESS_ACTOR,
            "DataObject": ElementNamingPattern.DATA_OBJECT
        }

        pattern_key = type_mapping.get(element_type, ElementNamingPattern.APPLICATION_COMPONENT)
        return self.naming_patterns[pattern_key]

    def _apply_pattern(self, name: str, pattern: Dict, technology: Optional[str] = None) -> str:
        """Aplica o padrão de nomenclatura ao nome"""
        result = name

        # Aplicar estilo
        if pattern["style"] == "PascalCase":
            result = self._to_pascal_case(result)
        elif pattern["style"] == "Title Case":
            result = result.title()

        # Adicionar prefixo se não existir
        if pattern["prefix"] and not result.startswith(pattern["prefix"]):
            result = f"{pattern['prefix']}{result}"

        # Adicionar sufixo se não existir
        if pattern["suffix"] and not result.endswith(pattern["suffix"]):
            # Evitar duplicação se já contém a palavra
            suffix_word = pattern["suffix"].lower()
            if suffix_word not in result.lower():
                result = f"{result} {pattern['suffix']}"

        # Adicionar tecnologia se especificada
        if technology:
            tech_name = self.technology_mappings.get(technology.lower(), technology)
            if tech_name not in result:
                result = f"{result} ({tech_name})"

        return result

    def _to_pascal_case(self, text: str) -> str:
        """Converte texto para PascalCase"""
        # Remove caracteres especiais e divide em palavras
        words = re.findall(r'\w+', text)

        # Capitaliza primeira letra de cada palavra
        pascal_words = [word.capitalize() for word in words if word]

        return ''.join(pascal_words) if pascal_words else text

    def suggest_improvements(self, elements: List[Dict]) -> List[Dict]:
        """
        Sugere melhorias de nomenclatura para uma lista de elementos

        Args:
            elements: Lista de elementos com 'name', 'type', 'technology' (opcional)

        Returns:
            List[Dict]: Lista de sugestões com 'original', 'suggested', 'reason'
        """
        suggestions = []

        for element in elements:
            original_name = element.get("name", "")
            element_type = element.get("type", "")
            technology = element.get("technology", "")

            suggested_name = self.apply_naming_conventions(original_name, element_type, technology)

            if suggested_name != original_name:
                reason = self._generate_improvement_reason(original_name, suggested_name, element_type)
                suggestions.append({
                    "element_id": element.get("id", ""),
                    "original": original_name,
                    "suggested": suggested_name,
                    "reason": reason,
                    "type": element_type
                })

        return suggestions

    def _generate_improvement_reason(self, original: str, suggested: str, element_type: str) -> str:
        """Gera explicação para a melhoria sugerida"""
        reasons = []

        if original.lower() != suggested.lower():
            if len(suggested) > len(original):
                reasons.append("Nome mais descritivo")

            if any(char.isupper() for char in suggested) and not any(char.isupper() for char in original):
                reasons.append("Aplicação de PascalCase")

            if "Service" in suggested and "Service" not in original:
                reasons.append("Adição de sufixo apropriado")

            if "(" in suggested and ")" in suggested:
                reasons.append("Indicação de tecnologia")

        if not reasons:
            reasons.append("Melhoria geral de nomenclatura")

        return " | ".join(reasons)


class C4NamingStandards:
    """Padrões específicos de nomenclatura para diagramas C4"""

    CONTAINER_TYPES = {
        "web_application": "Web Application",
        "mobile_app": "Mobile App",
        "api": "API",
        "database": "Database",
        "message_queue": "Message Queue",
        "cache": "Cache",
        "file_storage": "File Storage"
    }

    ACTOR_ROLES = {
        "user": "User",
        "admin": "Administrator",
        "customer": "Customer",
        "operator": "System Operator",
        "external_system": "External System"
    }

    RELATIONSHIP_LABELS = {
        "uses": "uses",
        "calls": "makes API calls to",
        "reads": "reads from",
        "writes": "writes to",
        "sends": "sends messages to",
        "receives": "receives data from"
    }

    @staticmethod
    def standardize_container_name(name: str, container_type: str) -> str:
        """Padroniza nome de container baseado no tipo"""
        base_name = name.strip()

        if container_type in C4NamingStandards.CONTAINER_TYPES:
            type_suffix = C4NamingStandards.CONTAINER_TYPES[container_type]
            if not base_name.endswith(type_suffix):
                return f"{base_name} {type_suffix}"

        return base_name

    @staticmethod
    def standardize_actor_name(name: str, role: str = "user") -> str:
        """Padroniza nome de ator baseado no papel"""
        base_name = name.strip()

        if role in C4NamingStandards.ACTOR_ROLES:
            standard_role = C4NamingStandards.ACTOR_ROLES[role]
            if base_name.lower() == role.lower():
                return standard_role

        return base_name

    @staticmethod
    def standardize_relationship_label(source_type: str, target_type: str,
                                     interaction_type: str = "uses") -> str:
        """Gera label padronizado para relacionamento"""
        return C4NamingStandards.RELATIONSHIP_LABELS.get(interaction_type, "interacts with")


# ===== FUNÇÕES DE CONVENIÊNCIA =====

def apply_naming_improvements(elements: List[Dict]) -> List[Dict]:
    """
    Função de conveniência para aplicar melhorias de nomenclatura

    Args:
        elements: Lista de elementos para melhorar

    Returns:
        List[Dict]: Sugestões de melhorias
    """
    applier = NamingConventionApplier()
    return applier.suggest_improvements(elements)


def improve_element_name(name: str, element_type: str, technology: str = None) -> str:
    """
    Função de conveniência para melhorar nome de um elemento

    Args:
        name: Nome atual
        element_type: Tipo do elemento
        technology: Tecnologia (opcional)

    Returns:
        str: Nome melhorado
    """
    applier = NamingConventionApplier()
    return applier.apply_naming_conventions(name, element_type, technology)


def validate_naming_compliance(elements: List[Dict]) -> Dict[str, any]:
    """
    Valida conformidade com padrões de nomenclatura

    Args:
        elements: Lista de elementos para validar

    Returns:
        Dict: Relatório de conformidade
    """
    applier = NamingConventionApplier()
    suggestions = applier.suggest_improvements(elements)

    total_elements = len(elements)
    elements_needing_improvement = len(suggestions)
    compliance_rate = ((total_elements - elements_needing_improvement) / total_elements * 100) if total_elements > 0 else 100

    return {
        "compliance_rate": compliance_rate,
        "total_elements": total_elements,
        "elements_needing_improvement": elements_needing_improvement,
        "suggestions": suggestions,
        "is_compliant": compliance_rate >= 80  # 80% ou mais é considerado conforme
    }
