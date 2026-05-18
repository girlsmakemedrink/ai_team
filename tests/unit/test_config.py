from core.config import Settings, get_settings


def test_settings_load_with_defaults() -> None:
    s = Settings()
    assert s.owner_token.get_secret_value()
    assert s.hmac_secret.get_secret_value()
    assert s.llm_model_haiku.startswith("claude-haiku")
    assert s.llm_model_sonnet.startswith("claude-sonnet")
    assert s.llm_model_opus.startswith("claude-opus")
    assert s.api_port == 8000
    assert s.checkpoint_interval_min == 30


def test_quota_thresholds_are_ordered() -> None:
    s = Settings()
    assert 0 < s.llm_quota_soft_warn_pct < s.llm_quota_pause_pct < 100


def test_get_settings_is_cached() -> None:
    a = get_settings()
    b = get_settings()
    assert a is b


def test_target_repo_defaults() -> None:
    s = Settings()
    assert s.default_target_repo == "."
    assert s.default_target_repo_branch
