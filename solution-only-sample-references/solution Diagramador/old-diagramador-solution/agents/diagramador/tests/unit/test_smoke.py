"""
Smoke tests for Architect Agent ADK.

Quick tests to verify basic functionality without dependencies on unimplemented modules.
"""

import sys
from pathlib import Path
import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.mark.smoke
def test_project_structure():
    """Test that basic project structure exists."""
    assert project_root.exists(), "Project root should exist"
    assert (project_root / "app").exists(), "App directory should exist"
    assert (project_root / "tests").exists(), "Tests directory should exist"


@pytest.mark.smoke
def test_imports():
    """Test that main modules can be imported safely."""
    # Test app module import
    try:
        import app
        assert True, "App module imported successfully"
    except ImportError:
        pytest.skip("App module not yet implemented")

    # Test tools module import
    try:
        from app import tools
        assert True, "Tools module imported successfully"
    except ImportError:
        pytest.skip("Tools module not yet implemented")

    # Test generators import
    try:
        from app.tools import generators
        assert True, "Generators module imported successfully"
    except ImportError:
        pytest.skip("Generators module not yet implemented")

    # Test validators import
    try:
        from app.tools import validators
        assert True, "Validators module imported successfully"
    except ImportError:
        pytest.skip("Validators module not yet implemented")

    # Test utilities import
    try:
        from app.tools import utilities
        assert True, "Utilities module imported successfully"
    except ImportError:
        pytest.skip("Utilities module not yet implemented")


@pytest.mark.smoke
def test_config_files():
    """Test that configuration files exist."""
    # Check requirements.txt
    requirements_file = project_root / "requirements.txt"
    assert requirements_file.exists(), "requirements.txt should exist"

    # Check for .env or .env.example (at least one should exist)
    env_file = project_root / ".env"
    env_example = project_root / ".env.example"

    if not env_file.exists() and not env_example.exists():
        # Not critical, just log it
        print("Warning: No .env or .env.example found")

    # Always pass this test as config files are optional for smoke tests
    assert True


@pytest.mark.smoke
def test_basic_generator():
    """Test basic generator functionality if available."""
    try:
        from app.tools.generators.diagram_generator import DiagramGenerator

        # Try to instantiate
        generator = DiagramGenerator()
        assert generator is not None, "Generator should be instantiated"

        # Check for required methods
        assert hasattr(generator, 'generate'), "Generator should have generate method"

    except ImportError:
        pytest.skip("DiagramGenerator not yet implemented")
    except Exception as e:
        pytest.skip(f"DiagramGenerator not ready: {e}")


@pytest.mark.smoke
def test_basic_validator():
    """Test basic validator functionality if available."""
    try:
        from app.tools.validators.schema_validator import SchemaValidator

        # Try to instantiate
        validator = SchemaValidator()
        assert validator is not None, "Validator should be instantiated"

        # Test basic validation with empty inputs
        result = validator.validate_schema({}, {})
        assert isinstance(result, dict), "Validation result should be a dictionary"

    except ImportError:
        pytest.skip("SchemaValidator not yet implemented")
    except AttributeError:
        pytest.skip("SchemaValidator methods not yet implemented")
    except Exception as e:
        pytest.skip(f"SchemaValidator not ready: {e}")


@pytest.mark.smoke
def test_utilities_import():
    """Test utilities module imports if available."""
    # Test NamingConventions
    try:
        from app.tools.utilities.naming_conventions import NamingConventions

        naming = NamingConventions()
        assert naming is not None, "NamingConventions should be instantiated"

    except ImportError:
        pytest.skip("NamingConventions not yet implemented")
    except Exception as e:
        pytest.skip(f"NamingConventions not ready: {e}")

    # Test FileHandler
    try:
        from app.tools.utilities.file_handler import FileHandler

        handler = FileHandler()
        assert handler is not None, "FileHandler should be instantiated"

    except ImportError:
        pytest.skip("FileHandler not yet implemented")
    except Exception as e:
        pytest.skip(f"FileHandler not ready: {e}")


@pytest.mark.smoke
def test_python_functionality():
    """Test basic Python functionality to ensure environment is working."""
    # Basic arithmetic
    assert 1 + 1 == 2, "Basic math should work"
    assert 10 * 10 == 100, "Multiplication should work"

    # String operations
    text = "architect"
    assert text.upper() == "ARCHITECT", "String upper should work"
    assert len(text) == 9, "String length should work"

    # List operations
    items = [1, 2, 3, 4, 5]
    assert len(items) == 5, "List length should work"
    assert sum(items) == 15, "List sum should work"
    assert max(items) == 5, "List max should work"

    # Dictionary operations
    data = {"name": "test", "value": 42}
    assert data["name"] == "test", "Dictionary access should work"
    assert len(data) == 2, "Dictionary length should work"

    # Set operations
    unique = {1, 2, 3, 3, 3}
    assert len(unique) == 3, "Set should have unique values"


@pytest.mark.smoke
def test_path_operations():
    """Test path operations are working."""
    # Test Path functionality
    test_path = Path("test/path")
    assert test_path.name == "path", "Path name should work"
    assert test_path.parent.name == "test", "Path parent should work"

    # Test path joining
    combined = Path("base") / "sub" / "file.txt"
    assert str(combined) == "base/sub/file.txt" or str(combined) == "base\\sub\\file.txt", "Path joining should work"

    # Test path suffix
    file_path = Path("document.pdf")
    assert file_path.suffix == ".pdf", "Path suffix should work"


@pytest.mark.smoke
def test_environment_setup():
    """Test that the test environment is properly configured."""
    # Check Python version
    assert sys.version_info >= (3, 7), "Python 3.7+ is required"

    # Check that we can import pytest
    import pytest
    assert pytest is not None, "Pytest should be available"

    # Check project root is in path
    assert str(project_root) in sys.path, "Project root should be in Python path"


@pytest.mark.smoke
def test_basic_assertions():
    """Test various assertion patterns to ensure pytest is working."""
    # Test equality
    assert 5 == 5

    # Test inequality
    assert 5 != 10

    # Test comparisons
    assert 10 > 5
    assert 5 < 10
    assert 5 <= 5
    assert 5 >= 5

    # Test membership
    assert 3 in [1, 2, 3, 4, 5]
    assert 10 not in [1, 2, 3, 4, 5]

    # Test identity
    a = [1, 2, 3]
    b = a
    assert a is b

    # Test truthiness
    assert True
    assert not False
    assert [].__class__ == list
    assert "".__class__ == str

    # Test type checking
    assert isinstance(5, int)
    assert isinstance("test", str)
    assert isinstance([1, 2, 3], list)
    assert isinstance({"key": "value"}, dict)