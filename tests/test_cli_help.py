"""Guards against argparse help-text landmines: a bare '%' in an action's
`help=` string crashes when the parent parser's help is formatted (it's
run through % substitution), while `description=` does the opposite --
'%%' shows up literally unless escaped consistently. Exercising every
--help page in the tree catches this class of bug immediately rather than
only when a user happens to hit the specific broken subcommand.
"""

import argparse

import pytest

from money.cli import build_parser


def all_subparsers(parser, prefix=()):
    """Yields (prog_path, parser) for the root parser and every subparser,
    recursively, by walking argparse's internal _SubParsersAction actions
    (not to be confused with an ordinary argument's `choices=[...]`, which
    is a list, not a dict of sub-parsers).
    """
    yield prefix, parser
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, subparser in action.choices.items():
                yield from all_subparsers(subparser, prefix + (name,))


@pytest.mark.parametrize(
    "prog_path",
    [path for path, _ in all_subparsers(build_parser())],
    ids=lambda p: " ".join(p) or "(root)",
)
def test_help_renders_without_crashing(prog_path):
    parser = build_parser()
    target = parser
    for name in prog_path:
        for action in target._actions:
            if isinstance(action, argparse._SubParsersAction) and name in action.choices:
                target = action.choices[name]
                break
    # format_help() exercises the same code path as `--help`, including
    # the %-substitution in action help strings and the (non-substituted)
    # description text -- raises on a bare unescaped '%' in either.
    help_text = target.format_help()
    assert help_text


def test_main_with_no_command_prints_help_and_exits_nonzero(capsys):
    from money.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0
    assert "usage: money" in capsys.readouterr().out
