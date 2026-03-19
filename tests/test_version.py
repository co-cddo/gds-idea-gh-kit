"""Tests for the version currency check."""

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from gds_idea_gh_kit.version import _fetch_latest_version, check_tool_is_current

# ---- _fetch_latest_version ----

_SIMPLE_INDEX_HTML = b"""
<!DOCTYPE html>
<html>
  <body>
    <a href="gds_idea_gh_kit-0.2.0-py3-none-any.whl">gds_idea_gh_kit-0.2.0-py3-none-any.whl</a>
    <a href="gds_idea_gh_kit-0.3.0-py3-none-any.whl">gds_idea_gh_kit-0.3.0-py3-none-any.whl</a>
    <a href="gds_idea_gh_kit-0.3.1-py3-none-any.whl">gds_idea_gh_kit-0.3.1-py3-none-any.whl</a>
  </body>
</html>
"""


def _mock_urlopen(html: bytes = _SIMPLE_INDEX_HTML):
    """Return a context-manager mock that yields a response with the given HTML."""
    mock_response = MagicMock()
    mock_response.read.return_value = html
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


def test_fetch_latest_version_returns_highest():
    """Returns the highest version found in the index HTML."""
    with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
        result = _fetch_latest_version()
    assert result == "0.3.1"


def test_fetch_latest_version_single_entry():
    """Works when only one version is listed."""
    html = b'<a href="gds_idea_gh_kit-0.2.0-py3-none-any.whl">gds_idea_gh_kit-0.2.0</a>'
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(html)):
        result = _fetch_latest_version()
    assert result == "0.2.0"


def test_fetch_latest_version_network_error_returns_none():
    """Returns None silently when the network is unavailable."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("unreachable")):
        result = _fetch_latest_version()
    assert result is None


def test_fetch_latest_version_os_error_returns_none():
    """Returns None silently on a generic OS/socket error."""
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        result = _fetch_latest_version()
    assert result is None


def test_fetch_latest_version_empty_html_returns_none():
    """Returns None when the response contains no recognisable version links."""
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(b"<html></html>")):
        result = _fetch_latest_version()
    assert result is None


# ---- check_tool_is_current ----


def test_check_tool_is_current_no_output_when_up_to_date(capsys):
    """Prints nothing when the installed version matches the latest."""
    with (
        patch("gds_idea_gh_kit.version.__version__", "0.3.1"),
        patch("gds_idea_gh_kit.version._fetch_latest_version", return_value="0.3.1"),
    ):
        check_tool_is_current()

    assert capsys.readouterr().err == ""


def test_check_tool_is_current_no_output_when_ahead(capsys):
    """Prints nothing when the installed version is newer than the index."""
    with (
        patch("gds_idea_gh_kit.version.__version__", "0.4.0"),
        patch("gds_idea_gh_kit.version._fetch_latest_version", return_value="0.3.1"),
    ):
        check_tool_is_current()

    assert capsys.readouterr().err == ""


def test_check_tool_is_current_no_output_when_fetch_fails(capsys):
    """Prints nothing when the version fetch returns None."""
    with patch("gds_idea_gh_kit.version._fetch_latest_version", return_value=None):
        check_tool_is_current()

    assert capsys.readouterr().err == ""


def test_check_tool_is_current_warns_when_outdated(capsys):
    """Prints the new version number to stderr when outdated."""
    with (
        patch("gds_idea_gh_kit.version.__version__", "0.3.0"),
        patch("gds_idea_gh_kit.version._fetch_latest_version", return_value="0.3.1"),
        patch("click.confirm", return_value=True),
    ):
        check_tool_is_current()

    assert "0.3.1" in capsys.readouterr().err


def test_check_tool_is_current_shows_upgrade_commands(capsys):
    """The warning includes both upgrade commands."""
    with (
        patch("gds_idea_gh_kit.version.__version__", "0.3.0"),
        patch("gds_idea_gh_kit.version._fetch_latest_version", return_value="0.3.1"),
        patch("click.confirm", return_value=True),
    ):
        check_tool_is_current()

    err = capsys.readouterr().err
    assert "idea-tools upgrade gds-idea-gh-kit" in err
    assert "uv tool upgrade gds-idea-gh-kit" in err
    assert "OR" in err


def test_check_tool_is_current_exits_when_user_declines():
    """Exits cleanly when the user answers No."""
    with (
        patch("gds_idea_gh_kit.version.__version__", "0.3.0"),
        patch("gds_idea_gh_kit.version._fetch_latest_version", return_value="0.3.1"),
        patch("click.confirm", return_value=False),
        pytest.raises(SystemExit) as exc_info,
    ):
        check_tool_is_current()

    assert exc_info.value.code == 0


def test_check_tool_is_current_continues_when_user_accepts():
    """Does not exit when the user answers Yes."""
    with (
        patch("gds_idea_gh_kit.version.__version__", "0.3.0"),
        patch("gds_idea_gh_kit.version._fetch_latest_version", return_value="0.3.1"),
        patch("click.confirm", return_value=True),
    ):
        check_tool_is_current()  # should not raise
