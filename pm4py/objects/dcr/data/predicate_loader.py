"""
Predicate loader for data-aware DCR graphs.

Loads user-defined Python predicate functions from an external file and
validates them for use as custom guard evaluators.  Predicates are called
during guard evaluation with the values of DCR events from the marking
(``marking.event_values``) as positional arguments.

A predicate file is a plain Python module that defines one or more
top-level public functions, each returning a ``bool``.  Example::

    # predicates.py
    def high_value(amount):
        return isinstance(amount, (int, float)) and amount > 1000

    def same_category(cat_a, cat_b):
        return isinstance(cat_a, str) and isinstance(cat_b, str) \\
               and cat_a.strip().lower() == cat_b.strip().lower()

These predicates can then be referenced in guard expressions::

    requiresApproval([Amount])          # unary — one event value
    same_category([CategoryA], [CategoryB])  # binary — two event values

The guard string is parsed by :func:`~pm4py.objects.dcr.data.expression_parser.parse_guard`
into a :class:`~pm4py.objects.dcr.data.expressions.FunctionCallExpression` AST node,
which resolves the function from the graph's ``predicate_registry`` at
evaluation time.

Usage
-----
::

    from pm4py.objects.dcr.data.predicate_loader import load_predicates

    graph = DataDcrGraph(...)
    graph.predicate_registry = load_predicates("path/to/predicates.py")

    # Or resolve from a file AND an in-memory dict simultaneously:
    graph.predicate_registry = resolve_predicates(
        predicate_file_path="predicates.py",
        predicate_functions={"extra_check": lambda x: x > 0},
    )

Adapted from the predicate loading mechanism in *Declare4PyRM* (2024),
which pioneered injectable predicates for Declare conformance checking.
"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, Optional

DataPredicate = Callable[..., bool]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_predicate(name: str, predicate: DataPredicate) -> None:
    """Raise ``RuntimeError`` if *predicate* cannot be used as a DCR guard predicate."""
    if not name.isidentifier() or name.startswith("_"):
        raise RuntimeError(
            f"Invalid predicate name '{name}'. "
            "Predicates must be public Python identifiers (no leading underscores)."
        )

    if not callable(predicate):
        raise RuntimeError(f"Predicate '{name}' must be callable.")

    sig = inspect.signature(predicate)
    required_positional = 0
    has_var_positional = False

    for param in sig.parameters.values():
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            has_var_positional = True
            continue
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            if param.default is inspect.Parameter.empty:
                required_positional += 1
            continue
        if (
            param.kind == inspect.Parameter.KEYWORD_ONLY
            and param.default is inspect.Parameter.empty
        ):
            raise RuntimeError(
                f"Predicate '{name}' has a required keyword-only parameter, "
                "which is not supported."
            )

    if has_var_positional:
        return

    if required_positional < 1:
        raise RuntimeError(
            f"Predicate '{name}' must accept at least one positional argument "
            f"(found {required_positional})."
        )


def _extract_predicates(module: ModuleType) -> Dict[str, DataPredicate]:
    """Extract and validate all public functions defined in *module*."""
    predicates: Dict[str, DataPredicate] = {}

    for name, value in vars(module).items():
        if name.startswith("_"):
            continue
        if inspect.isfunction(value) and value.__module__ == module.__name__:
            _validate_predicate(name, value)
            predicates[name] = value

    if not predicates:
        raise RuntimeError(
            "No public predicate functions found in predicate file. "
            "Define one or more top-level functions that return bool."
        )

    return predicates


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_predicates(predicate_file_path: Optional[str]) -> Dict[str, DataPredicate]:
    """
    Load predicate functions from a Python source file.

    Parameters
    ----------
    predicate_file_path : str or None
        Path to the predicates file.  Returns an empty dict when ``None``.

    Returns
    -------
    Dict[str, DataPredicate]
        Mapping from function name to callable.

    Raises
    ------
    RuntimeError
        If the file does not exist, cannot be imported, or contains no valid
        public predicate functions.
    """
    if predicate_file_path is None:
        return {}

    path = Path(predicate_file_path).expanduser()
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"Predicate file not found: {path}")

    module_name = f"pm4py_dcr_user_predicates_{abs(hash(path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import predicate file: {path}")

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to execute predicate file '{path}': {exc}"
        ) from exc

    return _extract_predicates(module)


def resolve_predicates(
    predicate_file_path: Optional[str] = None,
    predicate_functions: Optional[Dict[str, DataPredicate]] = None,
) -> Dict[str, DataPredicate]:
    """
    Resolve predicates from a file path and/or an in-memory dict.

    Both sources are merged.  A ``RuntimeError`` is raised if the same name
    appears in both with different functions.

    Parameters
    ----------
    predicate_file_path : str, optional
        Path to a Python predicates file.
    predicate_functions : dict, optional
        Directly supplied ``{name: callable}`` mapping.

    Returns
    -------
    Dict[str, DataPredicate]
        Merged mapping from function name to callable.
    """
    resolved: Dict[str, DataPredicate] = {}

    if predicate_functions:
        for name, predicate in predicate_functions.items():
            _validate_predicate(name, predicate)
            resolved[name] = predicate

    file_predicates = load_predicates(predicate_file_path)
    for name, predicate in file_predicates.items():
        if name in resolved and resolved[name] is not predicate:
            raise RuntimeError(
                f"Duplicate predicate '{name}' provided in both "
                "'predicate_functions' and the predicate file."
            )
        resolved[name] = predicate

    return resolved
