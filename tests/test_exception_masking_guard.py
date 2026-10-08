"""Guard against the repo's most recurrent bug class: raw exception text in logs.

Every `except ... as e:` handler under app/ must pass exception-derived values
through mask_exception_message()/mask_string() before logging them.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"

LOG_METHODS = {
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "critical",
    "exception",
    "log",
}
MASKERS = {"mask_exception_message", "mask_string", "type"}


def _raw_refs(node, tainted, masked=False):
    """Yield references to `tainted` names that no masking call encloses."""
    if isinstance(node, ast.Call):
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        masked = masked or name in MASKERS
    if isinstance(node, ast.Name) and node.id in tainted and not masked:
        yield node
        return
    for child in ast.iter_child_nodes(node):
        yield from _raw_refs(child, tainted, masked)


def _tainted_names(handler):
    """The exception name plus anything assigned from it, e.g. `msg = str(exc)`."""
    tainted = {handler.name}
    while True:
        grown = set(tainted)
        for node in ast.walk(handler):
            if isinstance(node, ast.Assign) and next(
                _raw_refs(node.value, tainted), None
            ):
                grown |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        if grown == tainted:
            return tainted
        tainted = grown


def _handler_violations(handler):
    tainted = _tainted_names(handler)
    for node in ast.walk(handler):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in LOG_METHODS
        ):
            continue
        if any(kw.arg == "exc_info" for kw in node.keywords):
            yield node.lineno, "exc_info= logs the unmasked exception message"
        for arg in node.args + [
            kw.value for kw in node.keywords if kw.arg != "exc_info"
        ]:
            for ref in _raw_refs(arg, tainted):
                yield ref.lineno, f"{ref.id!r} logged without mask_exception_message()"


def scan(tree):
    return {
        (line, why)
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.name
        for line, why in _handler_violations(node)
    }


def test_app_logs_no_unmasked_exception_text():
    violations = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        rel = path.relative_to(APP_DIR.parent)
        violations |= {f"{rel}:{line}: {why}" for line, why in scan(tree)}

    assert not violations, "Unmasked exception text reaches a log line:\n" + "\n".join(
        sorted(violations)
    )


@pytest.mark.parametrize(
    "body",
    [
        'logger.error("failed: %s", exc)',
        'logger.error(f"failed: {exc}")',
        'logger.warning("failed: {}".format(exc))',
        'logger.error("failed: %s", str(exc))',
        'msg = str(exc)\n    logger.error("failed: %s", msg)',
        'logger.error("failed", exc_info=True)',
    ],
)
def test_guard_detects_unmasked(body):
    assert scan(ast.parse(f"try:\n    pass\nexcept Exception as exc:\n    {body}"))


@pytest.mark.parametrize(
    "body",
    [
        'logger.error("failed: %s", mask_exception_message(exc))',
        'logger.error(f"failed: {mask_exception_message(exc)}")',
        'msg = mask_exception_message(exc)\n    logger.error("failed: %s", msg)',
        'logger.error("failed: %s", type(exc).__name__)',
        'logger.error("failed")',
    ],
)
def test_guard_accepts_masked(body):
    assert not scan(ast.parse(f"try:\n    pass\nexcept Exception as exc:\n    {body}"))
