from pathlib import Path

from clearact.settings import load_settings


def test_single_file_settings_favor_large_transparent_runs():
    settings = load_settings(Path(__file__).parents[2])
    assert settings.agent.max_iterations == 80
    assert settings.agent.max_tool_calls_per_run == 240
    assert settings.network.allow_localhost is True
    # Credentials can be supplied through clearact.json or an environment variable;
    # settings loading must preserve either form without exposing it to the web API.
    assert isinstance(settings.models["profiles"]["openai"]["api_key"], str)


def test_environment_style_keys_are_normalized_for_runtime():
    settings = load_settings(Path(__file__).parents[2])
    profile = settings.models["profiles"]["deepseek"]
    assert profile["base_url"] == "https://api.deepseek.com/v1"
    assert profile["api_key_env"] == "DEEPSEEK_API_KEY"
