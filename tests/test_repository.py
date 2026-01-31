"""Tests for repository operations."""

import pytest
import tempfile
from pathlib import Path

from memvcs.core.repository import Repository


class TestRepository:
    """Test repository functionality."""
    
    def test_init_repository(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(
                path=Path(tmpdir),
                author_name='Test',
                author_email='test@example.com'
            )
            
            assert repo.is_valid_repo()
            assert (repo.mem_dir / 'config.json').exists()
            assert (repo.current_dir / 'episodic').exists()
            assert (repo.current_dir / 'semantic').exists()
            assert (repo.current_dir / 'procedural').exists()
    
    def test_stage_and_commit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            
            # Create a file
            test_file = repo.current_dir / 'test.md'
            test_file.write_text('Test content')
            
            # Stage
            blob_hash = repo.stage_file('test.md')
            assert blob_hash is not None
            
            # Check staging
            staged = repo.staging.get_staged_files()
            assert 'test.md' in staged
            
            # Commit
            commit_hash = repo.commit('Test commit')
            assert commit_hash is not None
            
            # Staging should be cleared
            staged = repo.staging.get_staged_files()
            assert len(staged) == 0
    
    def test_branch_operations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            
            # Create initial commit
            test_file = repo.current_dir / 'test.md'
            test_file.write_text('Test')
            repo.stage_file('test.md')
            repo.commit('Initial commit')
            
            # Create branch
            result = repo.refs.create_branch('feature')
            assert result
            
            # List branches
            branches = repo.refs.list_branches()
            assert 'main' in branches
            assert 'feature' in branches
            
            # Switch branch
            repo.refs.set_head_branch('feature')
            assert repo.refs.get_current_branch() == 'feature'
    
    def test_get_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(path=Path(tmpdir))
            
            # Create some commits
            for i in range(3):
                test_file = repo.current_dir / f'test{i}.md'
                test_file.write_text(f'Content {i}')
                repo.stage_file(f'test{i}.md')
                repo.commit(f'Commit {i}')
            
            # Get log
            log = repo.get_log(max_count=10)
            assert len(log) == 3
            assert log[0]['message'] == 'Commit 2'
            assert log[1]['message'] == 'Commit 1'
            assert log[2]['message'] == 'Commit 0'
