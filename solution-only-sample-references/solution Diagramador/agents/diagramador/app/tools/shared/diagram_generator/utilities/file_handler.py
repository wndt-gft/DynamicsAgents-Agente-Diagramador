"""
File Handler Module
Manages file operations, directory creation, and output handling
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class OutputManager:
    """Manages output directory creation and file operations"""

    def __init__(self, base_output_dir: str = "outputs"):
        self.base_output_dir = Path(base_output_dir)

    def create_output_directory(self) -> Path:
        """
        Creates a timestamped output directory

        Returns:
            Path: Path to the created directory
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        story_id = f"story_{timestamp}"
        output_dir = self.base_output_dir / f"{story_id}_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"📁 Created output directory: {output_dir}")
        return output_dir

    def save_analysis(self, analysis: Dict[str, Any], output_dir: Path) -> Path:
        """
        Saves analysis results to JSON file

        Args:
            analysis: Analysis results dictionary
            output_dir: Directory to save the file

        Returns:
            Path: Path to the saved file
        """
        analysis_path = output_dir / "analysis.json"
        with open(analysis_path, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)

        logger.info(f"💾 Analysis saved to: {analysis_path}")
        return analysis_path

    def save_user_story(self, user_story: str, output_dir: Path) -> Path:
        """
        Saves original user story to text file

        Args:
            user_story: Original user story text
            output_dir: Directory to save the file

        Returns:
            Path: Path to the saved file
        """
        story_path = output_dir / "user_story.txt"
        story_path.write_text(user_story or "", encoding='utf-8')

        logger.info(f"📝 User story saved to: {story_path}")
        return story_path

    def save_diagram(self, content: str, diagram_type: str, output_dir: Path,
                    file_extension: str = "xml") -> Path:
        """
        Saves diagram content to file

        Args:
            content: Diagram content
            diagram_type: Type of diagram (context, container, component)
            output_dir: Directory to save the file
            file_extension: File extension (xml, puml, etc.)

        Returns:
            Path: Path to the saved file
        """
        filename = f"{diagram_type}_diagram.{file_extension}"
        file_path = output_dir / filename
        file_path.write_text(content, encoding='utf-8')

        logger.info(f"🎨 Diagram saved to: {file_path}")
        return file_path

    def list_output_files(self, output_dir: Path) -> list[str]:
        """
        Lists all files in the output directory

        Args:
            output_dir: Directory to list files from

        Returns:
            list[str]: List of filenames
        """
        try:
            return [file.name for file in output_dir.iterdir() if file.is_file()]
        except Exception as e:
            logger.error(f"Error listing files in {output_dir}: {e}")
            return []


class FileHandler(OutputManager):
    """Backward-compatible alias for legacy imports expecting ``FileHandler``."""

    def __init__(self, base_output_dir: str = "outputs"):
        super().__init__(base_output_dir)


def format_analysis_summary(analysis: Dict[str, Any]) -> str:
    """
    Formats analysis summary for user display

    Args:
        analysis: Analysis results dictionary

    Returns:
        str: Formatted summary
    """
    business_count = sum(len(v) if isinstance(v, list) else 1
                        for v in analysis.get('business_layer', {}).values())
    app_count = sum(len(v) if isinstance(v, list) else 1
                   for v in analysis.get('application_layer', {}).values())
    tech_count = sum(len(v) if isinstance(v, list) else 1
                    for v in analysis.get('technology_layer', {}).values())
    integration_count = len(analysis.get('integration_points', []))

    return f"""
✅ **User story analisada com sucesso!**

📊 **Resumo da análise:**
- 🏢 Camada de Negócio: {business_count} elementos
- 💻 Camada de Aplicação: {app_count} elementos  
- 🔧 Camada Tecnológica: {tech_count} elementos
- 🔗 Pontos de Integração: {integration_count}

🎨 **Qual diagrama você gostaria de gerar?**

Digite uma das opções:
- **context** - Diagrama de contexto (visão geral do sistema)
- **container** - Diagrama de containers (aplicações e bancos de dados)
- **component** - Diagrama de componentes (detalhes internos)
- **todos** - Gerar todos os diagramas

💡 **Exemplo**: Digite `context` para gerar o diagrama de contexto
"""


def format_generation_results(results: list, output_dir: Path, output_manager: OutputManager) -> str:
    """
    Formats diagram generation results for user display

    Args:
        results: List of (diagram_type, success, message) tuples
        output_dir: Output directory path
        output_manager: OutputManager instance

    Returns:
        str: Formatted results
    """
    response = f"📂 **Arquivos gerados em:** `{output_dir}`\n\n"

    for diag_type, success, message in results:
        if success:
            response += f"✅ **{diag_type.title()}**: {message}\n"
        else:
            response += f"❌ **{diag_type.title()}**: {message}\n"

    response += f"\n📄 **Arquivos criados:**\n"
    files = output_manager.list_output_files(output_dir)
    for file in files:
        response += f"- {file}\n"

    return response


__all__ = [
    "OutputManager",
    "FileHandler",
    "format_analysis_summary",
    "format_generation_results",
]
