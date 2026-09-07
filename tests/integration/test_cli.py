from clearact import cli


def test_project_root_resolves_to_repository_root():
    assert (cli._project_root() / "clearact.json").is_file()


def test_load_dotenv_does_not_override_existing_environment(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("CLEARACT_TEST_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("CLEARACT_TEST_KEY", "from-environment")

    cli._load_dotenv(tmp_path)

    assert cli.os.environ["CLEARACT_TEST_KEY"] == "from-environment"
