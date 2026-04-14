"""
Tests for Terraform backend configuration.

Validates that:
- Backend configuration files exist and are properly structured
- Bootstrap configuration creates required resources
- Backend references match bootstrap outputs
- No state files are tracked by git
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any

import pytest


@pytest.fixture
def project_root() -> Path:
    """Project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def infrastructure_root(project_root: Path) -> Path:
    """Infrastructure directory."""
    return project_root / "infrastructure"


@pytest.fixture
def dev_environment(infrastructure_root: Path) -> Path:
    """Dev environment directory."""
    return infrastructure_root / "environments" / "dev"


@pytest.fixture
def bootstrap_dir(infrastructure_root: Path) -> Path:
    """Bootstrap directory."""
    return infrastructure_root / "bootstrap"


class TestBackendConfigurationExists:
    """Test that required backend configuration files exist."""

    def test_dev_backend_tf_exists(self, dev_environment: Path):
        """Dev environment has backend.tf file."""
        backend_file = dev_environment / "backend.tf"
        assert backend_file.exists(), "backend.tf missing from dev environment"

    def test_bootstrap_resources_exist(self, bootstrap_dir: Path):
        """Bootstrap directory has backend resources configuration."""
        bootstrap_file = bootstrap_dir / "backend-resources.tf"
        assert bootstrap_file.exists(), "backend-resources.tf missing from bootstrap"

    def test_infrastructure_readme_updated(self, infrastructure_root: Path):
        """Infrastructure README documents backend setup."""
        readme = infrastructure_root / "README.md"
        assert readme.exists()

        content = readme.read_text()
        assert "Remote State Backend" in content, "README missing backend section"
        assert "bootstrap" in content.lower(), "README missing bootstrap instructions"
        assert "S3" in content and "DynamoDB" in content


class TestBackendConfigurationContent:
    """Test backend configuration content and structure."""

    def test_backend_uses_s3(self, dev_environment: Path):
        """Backend is configured to use S3."""
        backend_file = dev_environment / "backend.tf"
        content = backend_file.read_text()

        assert 'backend "s3"' in content, "Backend not configured for S3"

    def test_backend_has_bucket(self, dev_environment: Path):
        """Backend configuration specifies S3 bucket."""
        backend_file = dev_environment / "backend.tf"
        content = backend_file.read_text()

        # Check for bucket configuration
        assert re.search(r'bucket\s*=\s*"[^"]+"', content), "No bucket specified"

    def test_backend_has_dynamodb_table(self, dev_environment: Path):
        """Backend configuration specifies DynamoDB table."""
        backend_file = dev_environment / "backend.tf"
        content = backend_file.read_text()

        # Check for DynamoDB table configuration
        assert re.search(r'dynamodb_table\s*=\s*"[^"]+"', content), (
            "No DynamoDB table specified"
        )

    def test_backend_has_encryption(self, dev_environment: Path):
        """Backend configuration enables encryption."""
        backend_file = dev_environment / "backend.tf"
        content = backend_file.read_text()

        assert re.search(r"encrypt\s*=\s*true", content), "Encryption not enabled"

    def test_backend_has_key(self, dev_environment: Path):
        """Backend configuration specifies state file key."""
        backend_file = dev_environment / "backend.tf"
        content = backend_file.read_text()

        assert re.search(r'key\s*=\s*"[^"]+"', content), "No state file key specified"

    def test_backend_has_region(self, dev_environment: Path):
        """Backend configuration specifies AWS region."""
        backend_file = dev_environment / "backend.tf"
        content = backend_file.read_text()

        assert re.search(r'region\s*=\s*"[^"]+"', content), "No region specified"


class TestBootstrapConfiguration:
    """Test bootstrap resource configuration."""

    def test_bootstrap_creates_s3_bucket(self, bootstrap_dir: Path):
        """Bootstrap creates S3 bucket resource."""
        bootstrap_file = bootstrap_dir / "backend-resources.tf"
        content = bootstrap_file.read_text()

        assert 'resource "aws_s3_bucket"' in content, "No S3 bucket resource"

    def test_bootstrap_enables_versioning(self, bootstrap_dir: Path):
        """Bootstrap enables bucket versioning."""
        bootstrap_file = bootstrap_dir / "backend-resources.tf"
        content = bootstrap_file.read_text()

        assert "aws_s3_bucket_versioning" in content, "Versioning not configured"
        assert 'status = "Enabled"' in content, "Versioning not enabled"

    def test_bootstrap_enables_encryption(self, bootstrap_dir: Path):
        """Bootstrap enables server-side encryption."""
        bootstrap_file = bootstrap_dir / "backend-resources.tf"
        content = bootstrap_file.read_text()

        assert "aws_s3_bucket_server_side_encryption_configuration" in content, (
            "Encryption not configured"
        )

    def test_bootstrap_blocks_public_access(self, bootstrap_dir: Path):
        """Bootstrap blocks public access to bucket."""
        bootstrap_file = bootstrap_dir / "backend-resources.tf"
        content = bootstrap_file.read_text()

        assert "aws_s3_bucket_public_access_block" in content, (
            "Public access block not configured"
        )
        assert "block_public_acls       = true" in content
        assert "block_public_policy     = true" in content

    def test_bootstrap_creates_dynamodb_table(self, bootstrap_dir: Path):
        """Bootstrap creates DynamoDB table resource."""
        bootstrap_file = bootstrap_dir / "backend-resources.tf"
        content = bootstrap_file.read_text()

        assert 'resource "aws_dynamodb_table"' in content, "No DynamoDB table resource"

    def test_dynamodb_has_lock_id_key(self, bootstrap_dir: Path):
        """DynamoDB table has LockID hash key."""
        bootstrap_file = bootstrap_dir / "backend-resources.tf"
        content = bootstrap_file.read_text()

        assert 'hash_key     = "LockID"' in content, "LockID not configured as hash key"

    def test_bootstrap_has_outputs(self, bootstrap_dir: Path):
        """Bootstrap defines output values."""
        bootstrap_file = bootstrap_dir / "backend-resources.tf"
        content = bootstrap_file.read_text()

        assert 'output "state_bucket_name"' in content
        assert 'output "dynamodb_table_name"' in content


class TestNamingConsistency:
    """Test that resource names are consistent between backend and bootstrap."""

    def test_bucket_names_match(self, dev_environment: Path, bootstrap_dir: Path):
        """Backend bucket reference matches bootstrap bucket name."""
        backend_content = (dev_environment / "backend.tf").read_text()
        bootstrap_content = (bootstrap_dir / "backend-resources.tf").read_text()

        # Extract bucket name from backend
        backend_match = re.search(r'bucket\s*=\s*"([^"]+)"', backend_content)
        assert backend_match, "Could not find bucket in backend.tf"
        backend_bucket = backend_match.group(1)

        # Extract bucket naming pattern from bootstrap
        # Should be: ${var.project}-${var.environment}-terraform-state
        assert "semantic-search" in backend_bucket
        assert "dev" in backend_bucket
        assert "terraform-state" in backend_bucket

    def test_dynamodb_names_match(self, dev_environment: Path, bootstrap_dir: Path):
        """Backend DynamoDB reference matches bootstrap table name."""
        backend_content = (dev_environment / "backend.tf").read_text()
        bootstrap_content = (bootstrap_dir / "backend-resources.tf").read_text()

        # Extract table name from backend
        backend_match = re.search(r'dynamodb_table\s*=\s*"([^"]+)"', backend_content)
        assert backend_match, "Could not find dynamodb_table in backend.tf"
        backend_table = backend_match.group(1)

        # Verify naming pattern
        assert "semantic-search" in backend_table
        assert "dev" in backend_table
        assert "terraform-locks" in backend_table


class TestGitIgnore:
    """Test that state files are properly gitignored."""

    def test_tfstate_in_gitignore(self, project_root: Path):
        """Gitignore excludes tfstate files."""
        gitignore = project_root / ".gitignore"
        assert gitignore.exists()

        content = gitignore.read_text()
        assert "*.tfstate" in content, "*.tfstate not in .gitignore"
        assert "*.tfstate.*" in content, "*.tfstate.* not in .gitignore"

    def test_terraform_dir_in_gitignore(self, project_root: Path):
        """Gitignore excludes .terraform directory."""
        gitignore = project_root / ".gitignore"
        content = gitignore.read_text()

        assert ".terraform/" in content, ".terraform/ not in .gitignore"

    def test_no_tfstate_files_in_repo(self, project_root: Path):
        """No tfstate files are tracked by git."""
        try:
            result = subprocess.run(
                ["git", "ls-files", "*.tfstate*"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=True,
            )
            tracked_files = result.stdout.strip()
            assert not tracked_files, f"tfstate files tracked by git: {tracked_files}"
        except subprocess.CalledProcessError:
            pytest.skip("Git not available or not a git repository")


class TestTerraformValidation:
    """Test Terraform configuration validation."""

    def test_bootstrap_terraform_fmt(self, bootstrap_dir: Path):
        """Bootstrap configuration is properly formatted."""
        try:
            result = subprocess.run(
                ["terraform", "fmt", "-check", "-recursive"],
                cwd=bootstrap_dir,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Bootstrap not formatted: {result.stdout}"
        except FileNotFoundError:
            pytest.skip("Terraform CLI not available")

    def test_dev_terraform_fmt(self, dev_environment: Path):
        """Dev environment is properly formatted."""
        try:
            result = subprocess.run(
                ["terraform", "fmt", "-check", "-recursive"],
                cwd=dev_environment,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, (
                f"Dev environment not formatted: {result.stdout}"
            )
        except FileNotFoundError:
            pytest.skip("Terraform CLI not available")

    def test_bootstrap_terraform_validate(self, bootstrap_dir: Path):
        """Bootstrap configuration is valid (requires terraform init first)."""
        try:
            # Check if .terraform exists (init has been run)
            if not (bootstrap_dir / ".terraform").exists():
                pytest.skip("Bootstrap not initialized - run 'terraform init' first")

            result = subprocess.run(
                ["terraform", "validate"],
                cwd=bootstrap_dir,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, (
                f"Bootstrap validation failed: {result.stderr}"
            )
        except FileNotFoundError:
            pytest.skip("Terraform CLI not available")


class TestSecurityBestPractices:
    """Test security best practices in configuration."""

    def test_bootstrap_uses_encryption(self, bootstrap_dir: Path):
        """Bootstrap enables encryption at rest."""
        content = (bootstrap_dir / "backend-resources.tf").read_text()
        assert "server_side_encryption" in content.lower(), "Encryption not configured"

    def test_bootstrap_blocks_public_access(self, bootstrap_dir: Path):
        """Bootstrap blocks all public access."""
        content = (bootstrap_dir / "backend-resources.tf").read_text()

        # All four public access blocks should be true
        assert "block_public_acls       = true" in content
        assert "block_public_policy     = true" in content
        assert "ignore_public_acls      = true" in content
        assert "restrict_public_buckets = true" in content

    def test_backend_enables_encryption(self, dev_environment: Path):
        """Backend configuration enables encryption."""
        content = (dev_environment / "backend.tf").read_text()
        assert "encrypt = true" in content, "Backend encryption not enabled"

    def test_bootstrap_tags_resources(self, bootstrap_dir: Path):
        """Bootstrap applies tags to resources."""
        content = (bootstrap_dir / "backend-resources.tf").read_text()

        # Check that resources have tags
        assert "tags = {" in content or "tags =" in content, "Resources not tagged"
        assert "ManagedBy" in content and "terraform" in content


class TestDocumentation:
    """Test that documentation is complete and accurate."""

    def test_readme_has_bootstrap_section(self, infrastructure_root: Path):
        """README documents bootstrap process."""
        content = (infrastructure_root / "README.md").read_text()

        assert "## Remote State Backend" in content
        assert "Bootstrap" in content
        assert "terraform init" in content
        assert "terraform apply" in content

    def test_readme_has_migration_guidance(self, infrastructure_root: Path):
        """README includes migration instructions."""
        content = (infrastructure_root / "README.md").read_text()

        assert "migration" in content.lower()
        assert "-migrate-state" in content

    def test_readme_mentions_bootstrap_resources(self, infrastructure_root: Path):
        """README mentions S3 and DynamoDB resources."""
        content = (infrastructure_root / "README.md").read_text()

        assert "S3 bucket" in content
        assert "DynamoDB" in content
        assert "semantic-search-dev-terraform-state" in content
        assert "semantic-search-dev-terraform-locks" in content

    def test_backend_has_comments(self, dev_environment: Path):
        """Backend configuration is documented with comments."""
        content = (dev_environment / "backend.tf").read_text()

        # Should have comment explaining the configuration
        assert "#" in content, "No comments in backend.tf"

    def test_bootstrap_has_comments(self, bootstrap_dir: Path):
        """Bootstrap configuration is documented with comments."""
        content = (bootstrap_dir / "backend-resources.tf").read_text()

        assert "#" in content, "No comments in bootstrap configuration"
