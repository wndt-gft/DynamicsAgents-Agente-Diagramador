"""
XML Integrity Enforcer - Ferramenta para garantir integridade de arquivos XML
Versão 2.1 - Integrada ao pipeline de geração de diagramas com importação robusta
"""

import re
import xml.etree.ElementTree as ET
import xml.dom.minidom
import logging
from typing import Tuple, List, Optional

# Configurar logger
logger = logging.getLogger(__name__)

class XMLIntegrityEnforcer:
    """Classe para validação e correção de integridade referencial em arquivos XML ArchiMate"""

    def __init__(self):
        self.validation_errors = []
        self.fixes_applied = []

    @staticmethod
    def get_instance():
        """Factory method que sempre retorna uma instância válida do XMLIntegrityEnforcer"""
        try:
            return XMLIntegrityEnforcer()
        except Exception as e:
            logger.warning(f"Erro ao criar XMLIntegrityEnforcer: {e}")
            return None

    def validate_file(self, file_path: str) -> Tuple[bool, List[str]]:
        """
        Valida um arquivo XML.

        Args:
            file_path: Caminho para o arquivo XML

        Returns:
            Tuple[is_valid, errors_list]
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Reset dos contadores
            self.validation_errors = []

            # Validar estrutura XML básica
            try:
                ET.fromstring(content)
            except ET.ParseError as e:
                self.validation_errors.append(f"Erro de estrutura XML: {str(e)}")

            # Validar referências cruzadas
            cross_ref_issues = self._validate_cross_references(content)
            self.validation_errors.extend(cross_ref_issues)

            return len(self.validation_errors) == 0, self.validation_errors

        except Exception as e:
            return False, [f"Erro ao validar arquivo: {str(e)}"]

    def fix_file(self, file_path: str, backup: bool = True) -> bool:
        """
        Corrige um arquivo XML.

        Args:
            file_path: Caminho para o arquivo XML
            backup: Se deve criar backup do arquivo original

        Returns:
            bool: True se a correção foi bem-sucedida
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            success, fixed_content, _ = self.enforce_integrity(content, file_path)

            if backup:
                backup_path = f"{file_path}.backup"
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(content)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(fixed_content)

            return success
        except Exception as e:
            logger.error(f"Erro ao corrigir arquivo: {e}")
            return False

    def enforce_integrity(self, xml_content: str, file_path: Optional[str] = None) -> Tuple[bool, str, List[str]]:
        """
        Aplica todas as verificações e correções de integridade ao XML.

        Args:
            xml_content: Conteúdo XML como string
            file_path: Caminho do arquivo (opcional, para logs)

        Returns:
            Tuple[success, fixed_content, errors_found]
        """
        logger.info(f"Iniciando verificação de integridade XML{' para ' + file_path if file_path else ''}")

        try:
            # Reset dos contadores
            self.validation_errors = []
            self.fixes_applied = []

            # 1. Corrigir problemas estruturais básicos
            fixed_content = self._fix_basic_structural_issues(xml_content)

            # 2. Corrigir tags malformadas
            fixed_content = self._fix_malformed_tags(fixed_content)

            # 3. Corrigir caracteres especiais e encoding
            fixed_content = self._fix_encoding_issues(fixed_content)

            # 3.1. Remover atributos duplicados no elemento raiz <model>
            fixed_content = self._deduplicate_root_attributes(fixed_content)

            # 4. Validar e corrigir estrutura XML
            fixed_content = self._validate_and_fix_xml_structure(fixed_content)

            # 5. Aplicar formatação consistente
            fixed_content = self._apply_consistent_formatting(fixed_content)

            # 6. Validação final
            is_valid = self._final_validation(fixed_content)

            if is_valid:
                logger.info(f"XML validado com sucesso. Correções aplicadas: {len(self.fixes_applied)}")
                return True, fixed_content, self.fixes_applied
            else:
                logger.error(f"XML ainda contém erros após correções: {self.validation_errors}")
                return False, fixed_content, self.validation_errors

        except Exception as e:
            error_msg = f"Erro durante aplicação de integridade XML: {str(e)}"
            logger.error(error_msg)
            self.validation_errors.append(error_msg)
            return False, xml_content, self.validation_errors

    def _fix_basic_structural_issues(self, content: str) -> str:
        """Corrige problemas estruturais básicos do XML."""

        # Garantir declaração XML
        if not content.strip().startswith('<?xml'):
            content = '<?xml version="1.0" encoding="UTF-8"?>\n' + content
            self.fixes_applied.append("Adicionada declaração XML")

        # Remover caracteres de controle inválidos
        original_length = len(content)
        content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content)
        if len(content) < original_length:
            self.fixes_applied.append("Removidos caracteres de controle inválidos")

        # Garantir que não há múltiplas declarações XML
        xml_declarations = content.count('<?xml')
        if xml_declarations > 1:
            # Manter apenas a primeira
            first_decl_end = content.find('?>') + 2
            content = content[:first_decl_end] + re.sub(r'<\?xml[^>]*\?>', '', content[first_decl_end:])
            self.fixes_applied.append("Removidas declarações XML duplicadas")

        return content

    def _fix_malformed_tags(self, content: str) -> str:
        """Corrige tags malformadas comuns."""

        # Corrigir o problema específico </n> -> </name>
        malformed_count = content.count('</n>')
        if malformed_count > 0:
            content = content.replace('</n>', '</name>')
            self.fixes_applied.append(f"Corrigidas {malformed_count} tags </n> para </name>")

        # Corrigir tags auto-fechadas malformadas básicas
        content = re.sub(r'<(\w+)([^>]*)/\s*>', r'<\1\2/>', content)

        return content

    def _fix_encoding_issues(self, content: str) -> str:
        """Corrige problemas de encoding e caracteres especiais."""

        # Corrigir double-encoding
        if '&amp;amp;' in content:
            content = content.replace('&amp;amp;', '&amp;')
            self.fixes_applied.append("Corrigido double-encoding de &amp;")

        return content

    def _deduplicate_root_attributes(self, content: str) -> str:
        """Remove atributos duplicados no elemento raiz <model> preservando a primeira ocorrência.
        Foca especialmente em namespaces e schemaLocation, origem comum do erro 'duplicate attribute' na linha 2.
        """
        try:
            # Localizar a tag de abertura do <model ...>
            m = re.search(r'<model\b([^>]*)>', content)
            if not m:
                return content
            attrs_str = m.group(1)

            # Extrair pares atributo="valor" mantendo ordem
            pairs: List[Tuple[str, str]] = []
            seen: set = set()
            # Regex robusto para capturar atributos com aspas simples ou duplas
            for attr_m in re.finditer(r'\s+([^\s=]+)\s*=\s*("[^"]*"|\'[^\']*\')', attrs_str):
                name = attr_m.group(1)
                value = attr_m.group(2)
                if name not in seen:
                    pairs.append((name, value))
                    seen.add(name)
                else:
                    # Ignorar duplicatas
                    continue

            # Reconstruir string de atributos deduplicada
            new_attrs = ''.join([f' {n}={v}' for n, v in pairs])

            # Substituir no conteúdo
            start, end = m.span(1)
            new_content = content[:start] + new_attrs + content[end:]

            if new_attrs != attrs_str:
                self.fixes_applied.append("Removidos atributos duplicados no elemento raiz <model>")

            return new_content
        except Exception as e:
            logger.warning(f"Falha ao deduplicar atributos do elemento raiz: {e}")
            return content

    def _validate_and_fix_xml_structure(self, content: str) -> str:
        """Valida e corrige a estrutura XML."""

        try:
            # Tentar parsear o XML
            ET.fromstring(content)
            return content
        except ET.ParseError as e:
            error_msg = str(e)
            self.validation_errors.append(f"Erro de estrutura XML: {error_msg}")

            # Corrigir problemas de integridade referencial
            if "Key" in error_msg and "not found" in error_msg:
                content = self._fix_referential_integrity(content, error_msg)

            return content

    def _fix_referential_integrity(self, content: str, error_msg: str) -> str:
        """Corrige problemas de integridade referencial em XMLs ArchiMate."""

        try:
            # Extrair ID problemático da mensagem de erro
            id_match = re.search(r"value '([^']+)' not found", error_msg)
            if not id_match:
                return content

            missing_id = id_match.group(1)
            self.fixes_applied.append(f"Detectado ID ausente: {missing_id}")

            # Coletar todos os IDs existentes no documento
            existing_ids = set()
            id_pattern = re.compile(r'identifier="([^"]+)"')
            for match in id_pattern.finditer(content):
                existing_ids.add(match.group(1))

            # Remover elementos que referenciam IDs inexistentes
            content = self._remove_invalid_references(content, existing_ids)

            return content

        except Exception as e:
            self.validation_errors.append(f"Erro ao corrigir integridade referencial: {str(e)}")
            return content

    def _remove_invalid_references(self, content: str, existing_ids: set) -> str:
        """Remove elementos com referências inválidas."""

        try:
            root = ET.fromstring(content)

            # Encontrar e remover elementos com referências inválidas
            elements_to_remove = []

            for elem in root.iter():
                # Verificar atributos de referência
                for attr in ['source', 'target', 'elementRef', 'relationshipRef']:
                    ref_value = elem.get(attr)
                    if ref_value and ref_value not in existing_ids:
                        elements_to_remove.append(elem)
                        break

            # Remover elementos inválidos
            removed_count = 0
            for elem in elements_to_remove:
                parent = elem.getparent() if hasattr(elem, 'getparent') else None
                if parent is not None:
                    parent.remove(elem)
                    removed_count += 1

            if removed_count > 0:
                self.fixes_applied.append(f"Removidos {removed_count} elementos com referências inválidas")

            return ET.tostring(root, encoding='unicode', method='xml')

        except Exception as e:
            self.validation_errors.append(f"Erro ao remover referências inválidas: {str(e)}")
            return content

    def _validate_cross_references(self, content: str) -> List[str]:
        """Valida todas as referências cruzadas no XML."""

        issues = []

        try:
            root = ET.fromstring(content)

            # Coletar todos os IDs disponíveis
            all_ids = set()
            for elem in root.iter():
                elem_id = elem.get('identifier')
                if elem_id:
                    all_ids.add(elem_id)

            # Verificar todas as referências
            reference_attrs = ['source', 'target', 'elementRef', 'relationshipRef', 'archimateElement', 'archimateRelationship']

            for elem in root.iter():
                for attr in reference_attrs:
                    ref_value = elem.get(attr)
                    if ref_value and ref_value not in all_ids:
                        issues.append(f"Referência inválida: {attr}='{ref_value}' não encontrada no modelo")

        except Exception as e:
            issues.append(f"Erro na validação de referências cruzadas: {str(e)}")

        return issues

    def _apply_consistent_formatting(self, content: str) -> str:
        """Aplica formatação consistente ao XML."""

        try:
            # Parsear e reformatar o XML
            dom = xml.dom.minidom.parseString(content)
            formatted = dom.toprettyxml(indent="    ", encoding=None)

            # Remover linhas vazias extras
            lines = [line for line in formatted.split('\n') if line.strip()]
            return '\n'.join(lines)

        except Exception as e:
            logger.warning(f"Não foi possível aplicar formatação: {e}")
            return content

    def _final_validation(self, content: str) -> bool:
        """Validação final do XML."""

        try:
            ET.fromstring(content)
            # Validação adicional de referências cruzadas
            cross_ref_issues = self._validate_cross_references(content)
            if cross_ref_issues:
                self.validation_errors.extend(cross_ref_issues)
                return False
            return True
        except ET.ParseError as e:
            self.validation_errors.append(f"Validação final falhou: {str(e)}")
            return False

    def fix_referential_integrity_file(self, file_path: str) -> bool:
        """
        Método específico para corrigir problemas de integridade referencial em arquivo.

        Args:
            file_path: Caminho para o arquivo XML com problemas de referência

        Returns:
            bool: True se a correção foi bem-sucedida
        """
        try:
            # Ler arquivo
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            logger.info(f"🔧 Corrigindo integridade referencial em: {file_path}")

            # Validar referências cruzadas primeiro
            cross_ref_issues = self._validate_cross_references(content)

            if cross_ref_issues:
                logger.info(f"📊 Encontrados {len(cross_ref_issues)} problemas de referência")

                # Aplicar correções de integridade referencial
                fixed_content = self._fix_all_referential_issues(content)

                # Criar backup
                backup_path = f"{file_path}.backup"
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                # Salvar arquivo corrigido
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(fixed_content)

                logger.info(f"✅ Arquivo corrigido. Backup salvo em: {backup_path}")
                return True
            else:
                logger.info("✅ Nenhum problema de referência encontrado")
                return True

        except Exception as e:
            logger.error(f"❌ Erro ao corrigir arquivo: {e}")
            return False

    def _fix_all_referential_issues(self, content: str) -> str:
        """Corrige todos os problemas de integridade referencial encontrados."""

        try:
            root = ET.fromstring(content)

            # Coletar todos os IDs existentes
            existing_ids = set()
            for elem in root.iter():
                elem_id = elem.get('identifier')
                if elem_id:
                    existing_ids.add(elem_id)

            # Encontrar e corrigir referências inválidas
            reference_attrs = ['source', 'target', 'elementRef', 'relationshipRef', 'archimateElement', 'archimateRelationship']

            elements_to_remove = []
            for elem in root.iter():
                has_invalid_ref = False
                for attr in reference_attrs:
                    ref_value = elem.get(attr)
                    if ref_value and ref_value not in existing_ids:
                        logger.info(f"🔍 Referência inválida encontrada: {attr}='{ref_value}'")
                        has_invalid_ref = True
                        break

                if has_invalid_ref:
                    elements_to_remove.append(elem)

            # Remover elementos marcados
            removed = 0
            for elem in elements_to_remove:
                parent = elem.getparent() if hasattr(elem, 'getparent') else None
                if parent is not None:
                    parent.remove(elem)
                    removed += 1

            if removed > 0:
                self.fixes_applied.append(f"Removidos {removed} elementos com referências inválidas")

            return ET.tostring(root, encoding='unicode', method='xml')

        except Exception as e:
            logger.error(f"Erro ao corrigir referências: {e}")
            return content

# Conveniência: função de módulo para uso rápido em testes/calls externos
def enforce_xml_integrity(xml_content: str) -> Tuple[bool, str, List[str]]:
    """Aplica verificação e correções de integridade ao XML e retorna (success, fixed_content, messages)."""
    enforcer = XMLIntegrityEnforcer.get_instance()
    return enforcer.enforce_integrity(xml_content)
