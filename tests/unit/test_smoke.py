from gti_copilot import __version__
from gti_copilot.cli import build_parser, main


def test_version_is_string() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_cli_without_command_prints_help_and_exits_1(capsys) -> None:
    assert main([]) == 1
    assert "gti-copilot" in capsys.readouterr().err


def test_parser_has_version_flag() -> None:
    parser = build_parser()
    actions = {a.dest for a in parser._actions}
    assert "version" in actions
