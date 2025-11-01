"""
Unit Tests for ConfigManager
=============================

Comprehensive tests for the configuration management module.
Coverage Target: >95%

Author: Djalma Saraiva
"""

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

# Add project paths
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "app"))

# Import module to test
from app.tools.config_manager import ConfigManager, get_config, get_config_manager


class TestConfigManager(unittest.TestCase):
    """Test suite for ConfigManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_manager = ConfigManager(base_path=self.temp_dir)

        # Reset singleton for each test
        ConfigManager._instance = None

    def tearDown(self):
        """Clean up after tests."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        ConfigManager._instance = None

    def test_initialization(self):
        """Test ConfigManager initialization."""
        self.assertEqual(self.config_manager.base_path, os.path.abspath(self.temp_dir))
        self.assertEqual(self.config_manager._data, {})
        self.assertFalse(self.config_manager._loaded)

    def test_initialization_default_path(self):
        """Test ConfigManager with default path."""
        manager = ConfigManager()
        expected_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__).replace('tests/unit', 'app/tools'),
            '..', 'config'
        ))
        self.assertTrue(manager.base_path.endswith('config'))

    def test_load_yaml_files(self):
        """Test loading YAML configuration files."""
        # Create test YAML file
        yaml_content = """
agent:
  name: test_agent
  version: 1.0
settings:
  debug: true
  timeout: 30
"""
        yaml_file = os.path.join(self.temp_dir, 'adk_config.yaml')
        with open(yaml_file, 'w') as f:
            f.write(yaml_content)

        # Load configuration
        self.config_manager.load()

        # Verify data was loaded
        self.assertTrue(self.config_manager._loaded)
        self.assertEqual(self.config_manager.get('agent')['name'], 'test_agent')
        self.assertEqual(self.config_manager.get('settings')['debug'], True)

    def test_load_multiple_files(self):
        """Test loading and merging multiple configuration files."""
        # Create first config file
        config1 = """
key1: value1
shared: first
"""
        with open(os.path.join(self.temp_dir, 'adk_config.yaml'), 'w') as f:
            f.write(config1)

        # Create second config file
        config2 = """
key2: value2
shared: second
"""
        with open(os.path.join(self.temp_dir, 'mapping.yml'), 'w') as f:
            f.write(config2)

        # Load configuration
        self.config_manager.load()

        # Verify merging (later files override)
        self.assertEqual(self.config_manager.get('key1'), 'value1')
        self.assertEqual(self.config_manager.get('key2'), 'value2')
        self.assertEqual(self.config_manager.get('shared'), 'second')

    def test_load_with_missing_files(self):
        """Test loading when configuration files don't exist."""
        # No files in temp_dir
        self.config_manager.load()

        self.assertTrue(self.config_manager._loaded)
        self.assertEqual(self.config_manager._data, {})

    def test_load_with_invalid_yaml(self):
        """Test loading with invalid YAML content."""
        invalid_yaml = """
invalid: yaml: content
  - without proper
  structure
"""
        yaml_file = os.path.join(self.temp_dir, 'adk_config.yaml')
        with open(yaml_file, 'w') as f:
            f.write(invalid_yaml)

        # Should not raise exception
        self.config_manager.load()
        self.assertTrue(self.config_manager._loaded)

    def test_load_idempotent(self):
        """Test that load() is idempotent."""
        yaml_content = "test: value"
        yaml_file = os.path.join(self.temp_dir, 'adk_config.yaml')
        with open(yaml_file, 'w') as f:
            f.write(yaml_content)

        # First load
        self.config_manager.load()
        first_data = self.config_manager._data.copy()

        # Second load should not reload
        self.config_manager.load()
        self.assertEqual(self.config_manager._data, first_data)

    def test_get_method(self):
        """Test get() method with various scenarios."""
        yaml_content = """
existing_key: existing_value
nested:
  key: value
"""
        yaml_file = os.path.join(self.temp_dir, 'adk_config.yaml')
        with open(yaml_file, 'w') as f:
            f.write(yaml_content)

        # Test get existing key
        value = self.config_manager.get('existing_key')
        self.assertEqual(value, 'existing_value')

        # Test get non-existing key
        value = self.config_manager.get('non_existing')
        self.assertIsNone(value)

        # Test get with default
        value = self.config_manager.get('non_existing', 'default_value')
        self.assertEqual(value, 'default_value')

        # Test get nested
        value = self.config_manager.get('nested')
        self.assertEqual(value['key'], 'value')

    def test_get_triggers_load(self):
        """Test that get() triggers load if not loaded."""
        yaml_content = "auto_load: true"
        yaml_file = os.path.join(self.temp_dir, 'adk_config.yaml')
        with open(yaml_file, 'w') as f:
            f.write(yaml_content)

        # Not loaded yet
        self.assertFalse(self.config_manager._loaded)

        # Get should trigger load
        value = self.config_manager.get('auto_load')
        self.assertTrue(self.config_manager._loaded)
        self.assertEqual(value, True)

    def test_all_method(self):
        """Test all() method returns complete configuration."""
        yaml_content = """
key1: value1
key2: value2
key3:
  nested: value3
"""
        yaml_file = os.path.join(self.temp_dir, 'adk_config.yaml')
        with open(yaml_file, 'w') as f:
            f.write(yaml_content)

        all_config = self.config_manager.all()

        self.assertIsInstance(all_config, dict)
        self.assertEqual(all_config['key1'], 'value1')
        self.assertEqual(all_config['key2'], 'value2')
        self.assertEqual(all_config['key3']['nested'], 'value3')

    def test_all_triggers_load(self):
        """Test that all() triggers load if not loaded."""
        yaml_content = "test: value"
        yaml_file = os.path.join(self.temp_dir, 'adk_config.yaml')
        with open(yaml_file, 'w') as f:
            f.write(yaml_content)

        self.assertFalse(self.config_manager._loaded)

        all_config = self.config_manager.all()

        self.assertTrue(self.config_manager._loaded)
        self.assertEqual(all_config['test'], 'value')

    @patch('app.tools.config_manager.yaml')
    def test_load_without_yaml_module(self, mock_yaml):
        """Test loading when PyYAML is not available."""
        # Simulate yaml module not available
        mock_yaml = None

        with patch('app.tools.config_manager.yaml', None):
            manager = ConfigManager(base_path=self.temp_dir)
            manager.load()

            self.assertTrue(manager._loaded)
            self.assertEqual(manager._data, {})

    def test_non_dict_yaml_content(self):
        """Test handling non-dict YAML content."""
        yaml_content = "- item1\n- item2\n- item3"
        yaml_file = os.path.join(self.temp_dir, 'adk_config.yaml')
        with open(yaml_file, 'w') as f:
            f.write(yaml_content)

        self.config_manager.load()

        # Non-dict content should be ignored
        self.assertEqual(self.config_manager._data, {})

    def test_file_read_exception(self):
        """Test handling file read exceptions."""
        # Create a file that will cause read error
        yaml_file = os.path.join(self.temp_dir, 'adk_config.yaml')

        with patch('builtins.open', side_effect=IOError("Read error")):
            self.config_manager.load()

            # Should handle exception gracefully
            self.assertTrue(self.config_manager._loaded)

    def test_backup_file_loading(self):
        """Test loading backup configuration file."""
        backup_content = """
backup: true
version: backup
"""
        backup_file = os.path.join(self.temp_dir, 'adk_config.yaml.backup')
        with open(backup_file, 'w') as f:
            f.write(backup_content)

        self.config_manager.load()

        self.assertEqual(self.config_manager.get('backup'), True)
        self.assertEqual(self.config_manager.get('version'), 'backup')


class TestConfigManagerSingleton(unittest.TestCase):
    """Test singleton behavior of ConfigManager."""

    def setUp(self):
        """Reset singleton before each test."""
        ConfigManager._instance = None

    def tearDown(self):
        """Clean up after tests."""
        ConfigManager._instance = None

    def test_get_config_manager_singleton(self):
        """Test that get_config_manager returns singleton instance."""
        manager1 = get_config_manager()
        manager2 = get_config_manager()

        self.assertIs(manager1, manager2)

    def test_get_config_manager_thread_safe(self):
        """Test thread-safe singleton creation."""
        managers = []

        def create_manager():
            managers.append(get_config_manager())

        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=create_manager)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # All should be the same instance
        first_manager = managers[0]
        for manager in managers:
            self.assertIs(manager, first_manager)

    def test_get_config_function(self):
        """Test get_config helper function."""
        # Create test config
        with tempfile.TemporaryDirectory() as temp_dir:
            yaml_content = "test_key: test_value"
            yaml_file = os.path.join(temp_dir, 'adk_config.yaml')
            with open(yaml_file, 'w') as f:
                f.write(yaml_content)

            # Mock the singleton to use our test directory
            with patch('app.tools.config_manager.ConfigManager') as MockConfig:
                mock_instance = ConfigManager(base_path=temp_dir)
                mock_instance.load()
                MockConfig.return_value = mock_instance

                with patch('app.tools.config_manager.get_config_manager', return_value=mock_instance):
                    value = get_config('test_key')
                    self.assertEqual(value, 'test_value')

                    # Test with default
                    value = get_config('missing_key', 'default')
                    self.assertEqual(value, 'default')


class TestConfigManagerEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        ConfigManager._instance = None

    def tearDown(self):
        """Clean up after tests."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        ConfigManager._instance = None

    def test_unicode_content(self):
        """Test handling Unicode content in configuration."""
        yaml_content = """
unicode_text: "Configuração em português com acentuação"
emoji: "🚀 🎯 ✅"
chinese: "配置文件"
"""
        yaml_file = os.path.join(self.temp_dir, 'adk_config.yaml')
        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(yaml_content)

        manager = ConfigManager(base_path=self.temp_dir)

        self.assertEqual(manager.get('unicode_text'), "Configuração em português com acentuação")
        self.assertEqual(manager.get('emoji'), "🚀 🎯 ✅")
        self.assertEqual(manager.get('chinese'), "配置文件")

    def test_large_configuration(self):
        """Test handling large configuration files."""
        # Create large config
        large_config = "large_data:\n"
        for i in range(1000):
            large_config += f"  key_{i}: value_{i}\n"

        yaml_file = os.path.join(self.temp_dir, 'adk_config.yaml')
        with open(yaml_file, 'w') as f:
            f.write(large_config)

        manager = ConfigManager(base_path=self.temp_dir)
        data = manager.get('large_data')

        self.assertEqual(len(data), 1000)
        self.assertEqual(data['key_500'], 'value_500')

    def test_empty_configuration_files(self):
        """Test handling empty configuration files."""
        # Create empty file
        empty_file = os.path.join(self.temp_dir, 'adk_config.yaml')
        open(empty_file, 'w').close()

        manager = ConfigManager(base_path=self.temp_dir)
        manager.load()

        self.assertEqual(manager._data, {})
        self.assertTrue(manager._loaded)

    def test_all_config_files(self):
        """Test loading all expected configuration files."""
        # Create all expected files
        files_content = {
            'adk_config.yaml': 'adk: config1',
            'adk_config.yaml.backup': 'backup: config2',
            'mapping.yml': 'mapping: config3',
            'vocabulary.yml': 'vocabulary: config4'
        }

        for filename, content in files_content.items():
            with open(os.path.join(self.temp_dir, filename), 'w') as f:
                f.write(content)

        manager = ConfigManager(base_path=self.temp_dir)
        all_data = manager.all()

        # All files should be loaded
        self.assertEqual(all_data['adk'], 'config1')
        self.assertEqual(all_data['backup'], 'config2')
        self.assertEqual(all_data['mapping'], 'config3')
        self.assertEqual(all_data['vocabulary'], 'config4')


if __name__ == '__main__':
    unittest.main()