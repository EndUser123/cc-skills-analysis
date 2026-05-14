"""
Test DifferentialTracer git safety.

Verifies that DifferentialTracer.compare_traces() does not modify git state.
"""

import subprocess

# Add parent directory to path for imports
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.tracer_enhanced import DifferentialTracer


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository for testing."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(['git', 'init'], cwd=repo, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=repo, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=repo, check=True, capture_output=True)

    # Create a Python file
    test_file = repo / "test.py"
    test_file.write_text("print('version 1')\n")

    # Commit version 1
    subprocess.run(['git', 'add', 'test.py'], cwd=repo, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Version 1'], cwd=repo, check=True, capture_output=True)

    # Modify file for version 2
    test_file.write_text("print('version 2')\n")
    subprocess.run(['git', 'add', 'test.py'], cwd=repo, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Version 2'], cwd=repo, check=True, capture_output=True)

    return repo


@pytest.fixture
def original_head(git_repo: Path) -> str:
    """Get the original HEAD commit."""
    return subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=git_repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_differential_tracer_no_git_checkout(git_repo: Path, original_head: str):
    """Test that DifferentialTracer does not use git checkout."""
    target_file = git_repo / "test.py"

    # Create DifferentialTracer
    tracer = DifferentialTracer(target_file, 'HEAD~1', 'HEAD')

    # Mock the CodeTracer.to_dict() method to avoid actual TRACE execution
    with patch.object(tracer.working_tracer, 'to_dict') as mock_working:
        with patch.object(tracer.broken_tracer, 'to_dict') as mock_broken:
            mock_working.return_value = {'issues': []}
            mock_broken.return_value = {'issues': []}

            # Execute comparison
            result = tracer.compare_traces()

            # Verify result structure
            assert 'working_version' in result
            assert 'broken_version' in result
            assert 'new_issues' in result
            assert 'fixed_issues' in result

    # Verify HEAD is unchanged (no git checkout was used)
    current_head = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=git_repo, capture_output=True, text=True, check=True
    ).stdout.strip()

    assert current_head == original_head, "HEAD commit should not change"


def test_differential_tracer_uncommitted_changes_preserved(git_repo: Path):
    """Test that uncommitted changes are not lost."""
    target_file = git_repo / "test.py"

    # Create uncommitted changes
    target_file.write_text("print('uncommitted')\n")

    # Store original content
    original_content = target_file.read_text()

    # Create DifferentialTracer
    tracer = DifferentialTracer(target_file, 'HEAD~1', 'HEAD')

    # Mock the CodeTracer.to_dict() method
    with patch.object(tracer.working_tracer, 'to_dict') as mock_working:
        with patch.object(tracer.broken_tracer, 'to_dict') as mock_broken:
            mock_working.return_value = {'issues': []}
            mock_broken.return_value = {'issues': []}

            # Execute comparison
            tracer.compare_traces()

    # Verify uncommitted changes are preserved
    final_content = target_file.read_text()
    assert final_content == original_content, "Uncommitted changes should be preserved"


def test_differential_tracer_uses_git_show(git_repo: Path):
    """Test that DifferentialTracer uses git show instead of git checkout."""
    target_file = git_repo / "test.py"

    # Create DifferentialTracer
    tracer = DifferentialTracer(target_file, 'HEAD~1', 'HEAD')

    # Mock subprocess.run to track git commands
    git_commands = []

    original_run = subprocess.run

    def mock_run(cmd, *args, **kwargs):
        if cmd[0] == 'git':
            git_commands.append(' '.join(cmd))
        return original_run(cmd, *args, **kwargs)

    # Mock the CodeTracer.to_dict() method
    with patch.object(tracer.working_tracer, 'to_dict') as mock_working:
        with patch.object(tracer.broken_tracer, 'to_dict') as mock_broken:
            mock_working.return_value = {'issues': []}
            mock_broken.return_value = {'issues': []}

            with patch('subprocess.run', side_effect=mock_run):
                tracer.compare_traces()

    # Verify git show was used, git checkout was NOT used
    assert any('git show' in cmd for cmd in git_commands), "Should use git show"
    assert not any('git checkout' in cmd for cmd in git_commands), "Should NOT use git checkout"


def test_differential_tracer_with_real_files(git_repo: Path):
    """Integration test with actual file content comparison."""
    target_file = git_repo / "test.py"

    # Create DifferentialTracer
    tracer = DifferentialTracer(target_file, 'HEAD~1', 'HEAD')

    # Execute comparison (without mocking - uses temp files)
    result = tracer.compare_traces()

    # Verify result structure
    assert result['working_version'] == 'HEAD~1'
    assert result['broken_version'] == 'HEAD'
    assert isinstance(result['new_issues'], list)
    assert isinstance(result['fixed_issues'], list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
