"""Shared fixtures for tests."""

import pytest
import httpx
from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.github_client import GitHubClient


@pytest.fixture
def gh_client(httpx_mock: HTTPXMock) -> GitHubClient:
    """A GitHubClient with a fake token (no real auth needed)."""
    return GitHubClient(token="fake-token", org="co-cddo")
