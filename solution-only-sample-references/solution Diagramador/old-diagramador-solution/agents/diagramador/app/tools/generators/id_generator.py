"""
NCName ID Generator for BiZZdesign compatibility
Gera IDs únicos compatíveis com o formato NCName exigido pelo BiZZdesign
"""

import re
import uuid
from typing import Set, Dict

class NCNameIDGenerator:
    """Gerador de IDs compatível com NCName"""

    def __init__(self):
        self.used_ids: Set[str] = set()
        self.id_counters: Dict[str, int] = {}

    def generate_element_id(self, base_name: str) -> str:
        """
        Gera ID único para elemento baseado no nome

        Args:
            base_name: Nome base para gerar o ID

        Returns:
            ID único compatível com NCName
        """
        # Limpar e normalizar o nome base
        clean_name = self._clean_name(base_name)

        # Garantir que comece com letra
        if not clean_name or not clean_name[0].isalpha():
            clean_name = f"elem_{clean_name}" if clean_name else "element"

        # Gerar ID único
        return self._ensure_unique_id(clean_name)

    def generate_relationship_id(self, source: str, target: str) -> str:
        """
        Gera ID único para relacionamento

        Args:
            source: Nome/ID do elemento origem
            target: Nome/ID do elemento destino

        Returns:
            ID único para o relacionamento
        """
        source_clean = self._clean_name(source)
        target_clean = self._clean_name(target)

        base_name = f"rel_{source_clean}_to_{target_clean}"
        return self._ensure_unique_id(base_name)

    def generate_view_id(self, view_name: str) -> str:
        """
        Gera ID único para view/diagrama

        Args:
            view_name: Nome da view

        Returns:
            ID único para a view
        """
        clean_name = self._clean_name(view_name)
        base_name = f"view_{clean_name}" if clean_name else "view"

        return self._ensure_unique_id(base_name)

    def generate_visual_id(self, element_type: str, suffix: str = "") -> str:
        """
        Gera ID único para elemento visual

        Args:
            element_type: Tipo do elemento visual (node, connection, etc.)
            suffix: Sufixo opcional

        Returns:
            ID único para elemento visual
        """
        suffix_clean = f"_{self._clean_name(suffix)}" if suffix else ""
        base_name = f"{element_type}{suffix_clean}"

        return self._ensure_unique_id(base_name)

    def generate_ncname_id(self, base_name: str, readable_name: str = None) -> str:
        """
        Gera ID único compatível com NCName (método principal)

        Args:
            base_name: Nome base para gerar o ID
            readable_name: Nome legível opcional para usar como base (se fornecido)

        Returns:
            ID único compatível com NCName
        """
        # Usar readable_name se fornecido, senão usar base_name
        name_to_use = readable_name if readable_name else base_name
        return self.generate_element_id(name_to_use)

    def _clean_name(self, name: str) -> str:
        """
        Limpa nome para ser compatível com NCName

        Args:
            name: Nome a ser limpo

        Returns:
            Nome limpo compatível com NCName
        """
        if not name:
            return ""

        # Converter para string se necessário
        name = str(name)

        # Remover espaços e caracteres especiais, manter apenas letras, números, _ e -
        clean = re.sub(r'[^\w\-]', '_', name)

        # Remover underscores consecutivos
        clean = re.sub(r'_+', '_', clean)

        # Remover underscores no início e fim
        clean = clean.strip('_')

        # Converter para camelCase se tiver múltiplas palavras
        if '_' in clean:
            parts = clean.split('_')
            clean = parts[0].lower() + ''.join(word.capitalize() for word in parts[1:])

        # Garantir que não seja muito longo (NCName tem limitações práticas)
        if len(clean) > 50:
            clean = clean[:47] + str(abs(hash(name)) % 1000)

        return clean

    def _ensure_unique_id(self, base_id: str) -> str:
        """
        Garante que o ID seja único adicionando contador se necessário

        Args:
            base_id: ID base

        Returns:
            ID único
        """
        if not base_id:
            base_id = f"id_{uuid.uuid4().hex[:8]}"

        original_id = base_id
        counter = 1

        while base_id in self.used_ids:
            # Usar contador para garantir unicidade
            if original_id in self.id_counters:
                self.id_counters[original_id] += 1
            else:
                self.id_counters[original_id] = 1

            base_id = f"{original_id}_{self.id_counters[original_id]}"
            counter += 1

            # Failsafe para evitar loops infinitos
            if counter > 1000:
                base_id = f"{original_id}_{uuid.uuid4().hex[:8]}"
                break

        self.used_ids.add(base_id)
        return base_id

    def reset(self):
        """Reseta o gerador, limpando IDs usados"""
        self.used_ids.clear()
        self.id_counters.clear()

    def is_valid_ncname(self, name: str) -> bool:
        """
        Verifica se um nome é um NCName válido

        Args:
            name: Nome a ser verificado

        Returns:
            True se for NCName válido
        """
        if not name:
            return False

        # NCName pattern: deve começar com letra ou _, seguido de letras, dígitos, -, _, .
        ncname_pattern = r'^[a-zA-Z_][a-zA-Z0-9_\-\.]*$'

        return bool(re.match(ncname_pattern, name))

    def get_stats(self) -> Dict[str, int]:
        """
        Retorna estatísticas do gerador

        Returns:
            Dict com estatísticas
        """
        return {
            'total_ids_generated': len(self.used_ids),
            'unique_base_names': len(self.id_counters),
            'conflicts_resolved': sum(self.id_counters.values())
        }

# Instância global para uso em todo o sistema
global_id_generator = NCNameIDGenerator()

def generate_element_id(base_name: str) -> str:
    """Função de conveniência para gerar ID de elemento"""
    return global_id_generator.generate_element_id(base_name)

def generate_relationship_id(source: str, target: str) -> str:
    """Função de conveniência para gerar ID de relacionamento"""
    return global_id_generator.generate_relationship_id(source, target)

def generate_view_id(view_name: str) -> str:
    """Função de conveniência para gerar ID de view"""
    return global_id_generator.generate_view_id(view_name)

def reset_id_generator():
    """Reseta o gerador global de IDs"""
    global_id_generator.reset()
