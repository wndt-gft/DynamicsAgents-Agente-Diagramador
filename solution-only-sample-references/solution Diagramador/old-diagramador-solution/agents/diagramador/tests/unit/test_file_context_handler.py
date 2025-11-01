"""
Unit Tests for File Handler and Context Manager
================================================

Comprehensive tests for file handling and context management modules.
Coverage Target: >95%

Author: Djalma Saraiva
"""
# pylint: disable=import-error,no-name-in-module

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "app"))

# Import modules to test
from app.tools.utilities.file_handler import (  # noqa: E402
    OutputManager,
    format_analysis_summary,
    format_generation_results
)

from app.tools.utilities.context_manager import (  # noqa: E402
    AgentContext,
    get_agent_context
)


class TestOutputManager(unittest.TestCase):
    """Test OutputManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.output_manager = OutputManager()

    def tearDown(self):
        """Clean up after tests."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test OutputManager initialization."""
        manager = OutputManager()
        self.assertIsNotNone(manager)

        # Test with base_output_dir parameter
        manager_with_dir = OutputManager(base_output_dir=self.temp_dir)
        self.assertEqual(manager_with_dir.base_output_dir, Path(self.temp_dir))

    def test_save_diagram(self):
        """Test saving diagram content."""
        content = """<?xml version="1.0"?>
<diagram>
    <element>Test</element>
</diagram>"""

        diagram_type = "context"
        file_path = self.output_manager.save_diagram(
            content,
            diagram_type,
            Path(self.temp_dir)
        )

        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.suffix, '.xml')

        # Verify content
        saved_content = file_path.read_text(encoding='utf-8')
        self.assertEqual(saved_content, content)

    def test_save_diagram_with_extension(self):
        """Test saving diagram with different extensions."""
        content = "@startuml\n...\n@enduml"

        file_path = self.output_manager.save_diagram(
            content,
            "container",
            Path(self.temp_dir),
            file_extension="puml"
        )

        self.assertEqual(file_path.suffix, '.puml')
        self.assertTrue(file_path.exists())

    def test_list_output_files(self):
        """Test listing output files."""
        # Create test files
        test_files = ["file1.xml", "file2.puml", "file3.json"]
        for filename in test_files:
            (Path(self.temp_dir) / filename).touch()

        files = self.output_manager.list_output_files(Path(self.temp_dir))

        self.assertEqual(len(files), 3)
        for filename in test_files:
            self.assertIn(filename, files)

    def test_list_output_files_error(self):
        """Test error handling in list_output_files."""
        # Non-existent directory
        files = self.output_manager.list_output_files(Path("/nonexistent"))
        self.assertEqual(files, [])

    def test_save_analysis(self):
        """Test saving analysis results."""
        analysis = {
            'business_layer': {'actors': ['User']},
            'application_layer': {'services': ['AuthService']},
            'technology_layer': {'databases': ['PostgreSQL']}
        }

        file_path = self.output_manager.save_analysis(
            analysis,
            Path(self.temp_dir)
        )

        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.name, 'analysis.json')

        # Verify content
        with open(file_path, 'r', encoding='utf-8') as f:
            saved_analysis = json.load(f)
        self.assertEqual(saved_analysis, analysis)

    def test_save_user_story(self):
        """Test saving a user story."""
        story = "Como usuário, quero fazer login para acessar o sistema"

        file_path = self.output_manager.save_user_story(
            story,
            Path(self.temp_dir)
        )

        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.name, 'user_story.txt')

        # Verify content
        saved_story = file_path.read_text(encoding='utf-8')
        self.assertEqual(saved_story, story)

    def test_create_output_directory(self):
        """Test creating an output directory."""
        # create_output_directory() doesn't take parameters
        output_dir = self.output_manager.create_output_directory()

        self.assertTrue(output_dir.exists())
        self.assertTrue(output_dir.is_dir())

        # Directory name should contain a timestamp
        self.assertIn("story_", output_dir.name)


class TestFileFunctions(unittest.TestCase):
    """Test standalone file handling functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.output_manager = OutputManager()

    def tearDown(self):
        """Clean up after tests."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_format_analysis_summary(self):
        """Test formatting analysis summary."""
        analysis = {
            'business_layer': {
                'actors': ['User', 'Admin'],
                'processes': ['Login', 'Register']
            },
            'application_layer': {
                'services': ['AuthService'],
                'components': ['UserComponent']
            },
            'technology_layer': {
                'databases': ['PostgreSQL'],
                'servers': ['nginx']
            },
            'integration_points': ['API Gateway', 'Message Queue']
        }

        summary = format_analysis_summary(analysis)

        self.assertIn("Camada de Negócio", summary)
        self.assertIn("Camada de Aplicação", summary)
        self.assertIn("Camada Tecnológica", summary)
        self.assertIn("Pontos de Integração: 2", summary)

    def test_format_generation_results(self):
        """Test formatting generation results."""
        results = [
            ('context', True, 'Generated successfully'),
            ('container', True, 'Generated successfully'),
            ('component', False, 'Generation failed')
        ]

        # Create test files
        for filename in ['context.xml', 'container.xml']:
            (Path(self.temp_dir) / filename).touch()

        formatted = format_generation_results(
            results,
            Path(self.temp_dir),
            self.output_manager
        )

        self.assertIn("context", formatted.lower())
        self.assertIn("container", formatted.lower())
        self.assertIn("component", formatted.lower())
        self.assertIn("✅", formatted)
        self.assertIn("❌", formatted)


class TestAgentContext(unittest.TestCase):
    """Test AgentContext class."""

    def setUp(self):
        """Set up test fixtures."""
        self.context = AgentContext()

    def test_initialization(self):
        """Test AgentContext initialization."""
        context = AgentContext()
        self.assertIsNotNone(context)
        self.assertIsNone(context.last_analysis)
        self.assertIsNone(context.last_user_story)

    def test_set_and_get_analysis(self):
        """Test setting and getting analysis."""
        analysis = {
            'business_layer': {'actors': ['User']},
            'application_layer': {'services': ['Service']}
        }

        self.context.last_analysis = analysis
        self.assertEqual(self.context.last_analysis, analysis)

    def test_set_and_get_user_story(self):
        """Test setting and getting user story."""
        story = "Como usuário, quero fazer login"

        self.context.last_user_story = story
        self.assertEqual(self.context.last_user_story, story)

    def test_has_context(self):
        """Test checking if context exists."""
        self.assertFalse(self.context.has_context())

        self.context.last_analysis = {'test': 'data'}
        self.context.last_user_story = "test story"

        self.assertTrue(self.context.has_context())

    def test_clear_context(self):
        """Test clearing context."""
        self.context.last_analysis = {'test': 'data'}
        self.context.last_user_story = "test story"

        self.context.clear_context()

        self.assertIsNone(self.context.last_analysis)
        self.assertIsNone(self.context.last_user_story)
        self.assertFalse(self.context.has_context())

    def test_get_context_summary(self):
        """Test getting context summary."""
        # No context
        summary = self.context.get_context_summary()
        self.assertEqual(summary, "Nenhum contexto disponível")

        # With context
        self.context.last_analysis = {
            'business_layer': {'actors': ['User', 'Admin']}
        }
        self.context.last_user_story = "Como usuário, quero fazer login para acessar o sistema"

        summary = self.context.get_context_summary()
        self.assertIn("User story:", summary)
        self.assertIn("Elementos analisados:", summary)

    def test_context_summary_long_story(self):
        """Test context summary with a long story."""
        long_story = "Como " + "usuário " * 20 + "quero fazer algo"
        self.context.last_user_story = long_story
        self.context.last_analysis = {'business_layer': {'actors': []}}

        summary = self.context.get_context_summary()
        self.assertIn("...", summary)  # Should truncate long stories


class TestGlobalContext(unittest.TestCase):
    """Test global context functions."""

    def test_get_agent_context(self):
        """Test getting a global agent context."""
        context = get_agent_context()
        self.assertIsInstance(context, AgentContext)

        # Should return the same instance
        context2 = get_agent_context()
        self.assertIs(context, context2)

    def test_global_context_persistence(self):
        """Test that the global context persists."""
        context = get_agent_context()

        # Set some data
        context.last_user_story = "Test story"
        context.last_analysis = {"test": "data"}

        # Get again - should have the same data
        context2 = get_agent_context()
        self.assertEqual(context2.last_user_story, "Test story")
        self.assertEqual(context2.last_analysis, {"test": "data"})

        # Clean up
        context.clear_context()


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.output_manager = OutputManager()
        self.context = AgentContext()

    def tearDown(self):
        """Clean up after tests."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_empty_content(self):
        """Test saving empty content."""
        file_path = self.output_manager.save_diagram(
            "",
            "empty",
            Path(self.temp_dir)
        )

        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.read_text(), "")

    def test_save_unicode_content(self):
        """Test saving Unicode content."""
        unicode_content = "Conteúdo com acentuação: áéíóú ñ 中文 🚀"

        file_path = self.output_manager.save_diagram(
            unicode_content,
            "unicode",
            Path(self.temp_dir)
        )

        saved_content = file_path.read_text(encoding='utf-8')
        self.assertEqual(saved_content, unicode_content)

    def test_save_large_content(self):
        """Test saving large content."""
        large_content = "x" * (10 * 1024 * 1024)  # 10MB

        file_path = self.output_manager.save_diagram(
            large_content,
            "large",
            Path(self.temp_dir)
        )

        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.stat().st_size, len(large_content))

    def test_context_with_none_values(self):
        """Test context with None values."""
        self.context.last_analysis = None
        self.assertIsNone(self.context.last_analysis)

        # Setting None should work
        self.context.last_user_story = None
        self.assertIsNone(self.context.last_user_story)

        # has_context should be False with None values
        self.assertFalse(self.context.has_context())

    def test_context_with_complex_objects(self):
        """Test context with complex objects."""
        complex_analysis = {
            "business_layer": {
                "actors": ["User", "Admin"],
                "processes": ["Login", "Logout"]
            },
            "relationships": [
                {"from": "User", "to": "Login"},
                {"from": "Admin", "to": "Logout"}
            ],
            "metadata": {
                "version": "1.0",
                "timestamp": "2024-01-01"
            }
        }

        self.context.last_analysis = complex_analysis
        retrieved = self.context.last_analysis

        self.assertEqual(retrieved["business_layer"]["actors"], ["User", "Admin"])
        self.assertEqual(len(retrieved["relationships"]), 2)
        self.assertEqual(retrieved["metadata"]["version"], "1.0")

    def test_readonly_directory(self):
        """Test handling a readonly directory."""
        if os.name != 'nt':  # Unix-like systems only
            readonly_dir = Path(self.temp_dir) / "readonly"
            readonly_dir.mkdir()
            readonly_dir.chmod(0o444)

            try:
                # Should handle gracefully
                files = self.output_manager.list_output_files(readonly_dir)
                self.assertIsInstance(files, list)
            finally:
                readonly_dir.chmod(0o755)

    def test_special_characters_in_filename(self):
        """Test handling special characters in filenames."""
        special_chars = "file with spaces & special!@#"

        # Most filesystems will sanitize this
        file_path = self.output_manager.save_diagram(
            "content",
            special_chars,
            Path(self.temp_dir)
        )

        self.assertTrue(file_path.exists())


if __name__ == '__main__':
    unittest.main()