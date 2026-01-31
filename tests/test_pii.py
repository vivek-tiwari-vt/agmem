"""Unit tests for PII scanner: AWS keys detected, localhost IP ignored."""

import pytest

from memvcs.core.pii_scanner import PIIScanner, PIIIssue, PIIScanResult


class TestPIIScannerAWSKeys:
    """PII scanner must catch fake AWS keys."""

    def test_aws_access_key_detected(self):
        """Fake AWS access key (AKIA...) is detected."""
        # Use a key that does not contain 'example' so the false-positive filter does not skip it
        content = "AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF\n"
        issues = PIIScanner.scan_content(content, "memory.md")
        assert len(issues) >= 1
        aws_key_issues = [i for i in issues if i.issue_type == "aws_key"]
        assert len(aws_key_issues) == 1
        assert "AWS" in aws_key_issues[0].description

    def test_aws_secret_key_detected(self):
        """Fake AWS secret access key (40-char value) is detected."""
        # Use a 40-char value without 'example' so the false-positive filter does not skip it
        content = 'aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCY1234567890"\n'
        issues = PIIScanner.scan_content(content, "memory.md")
        assert len(issues) >= 1
        aws_secret_issues = [i for i in issues if i.issue_type == "aws_secret"]
        assert len(aws_secret_issues) == 1
        assert "secret" in aws_secret_issues[0].description.lower()

    def test_aws_key_and_secret_both_detected(self):
        """Content with both AWS key and secret reports both."""
        content = """
AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF
aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCY1234567890"
"""
        issues = PIIScanner.scan_content(content, "memory.md")
        types = {i.issue_type for i in issues}
        assert "aws_key" in types
        assert "aws_secret" in types


class TestPIIScannerLocalhostIgnored:
    """PII scanner must ignore 127.0.0.1 (localhost)."""

    def test_localhost_ip_ignored(self):
        """127.0.0.1 is not reported as PII (false positive filter)."""
        content = "Server: 127.0.0.1\nBind to 127.0.0.1:8000\n"
        issues = PIIScanner.scan_content(content, "memory.md")
        ip_issues = [i for i in issues if i.issue_type == "ip_address"]
        assert len(ip_issues) == 0

    def test_other_ip_still_detected(self):
        """A non-localhost IP is still reported (sanity check)."""
        content = "Remote: 203.0.113.50\n"
        issues = PIIScanner.scan_content(content, "memory.md")
        ip_issues = [i for i in issues if i.issue_type == "ip_address"]
        assert len(ip_issues) >= 1
