"""Tests for GitHubTargetRepo identifier parsing + clone + ops."""

from __future__ import annotations

import pytest

from core.target_repo.github import parse_github_identifier


def test_parse_owner_slash_repo() -> None:
    owner, repo, ssh_url = parse_github_identifier("girlsmakemedrink/telegram-tech-publisher")
    assert owner == "girlsmakemedrink"
    assert repo == "telegram-tech-publisher"
    assert ssh_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_parse_https_url() -> None:
    owner, repo, ssh_url = parse_github_identifier(
        "https://github.com/girlsmakemedrink/telegram-tech-publisher"
    )
    assert owner == "girlsmakemedrink"
    assert repo == "telegram-tech-publisher"
    assert ssh_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_parse_https_url_with_dot_git_suffix() -> None:
    _, repo, ssh_url = parse_github_identifier(
        "https://github.com/girlsmakemedrink/telegram-tech-publisher.git"
    )
    assert repo == "telegram-tech-publisher"
    assert ssh_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_parse_ssh_url_passthrough() -> None:
    owner, repo, ssh_url = parse_github_identifier(
        "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"
    )
    assert owner == "girlsmakemedrink"
    assert repo == "telegram-tech-publisher"
    assert ssh_url == "git@github.com:girlsmakemedrink/telegram-tech-publisher.git"


def test_parse_garbage_raises() -> None:
    with pytest.raises(ValueError, match="not a recognised GitHub identifier"):
        parse_github_identifier("not a repo")
