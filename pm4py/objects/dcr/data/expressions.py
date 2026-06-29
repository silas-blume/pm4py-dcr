"""
Expression system for DCR Graphs with data and decisions.

Implements the expression grammar from Definition 1 of [1]_:

    ExpE := BExpE | IExpE | void
    BExpE := eb | b | IExpE IBOp IExpE | BExpE BOp BExpE | not BExpE | if BExpE then BExpE else BExpE
    IExpE := ei | n | IExpE IOp IExpE | if BExpE then IExpE else IExpE
    IBOp := = | < | > | <= | >=
    IOp := + | - | *
    BOp := and | or

Expressions are represented as an AST (Abstract Syntax Tree) and evaluated
against a marking that maps events to their current values.

References
----------
.. [1] Hildebrandt, T.T., Normann, H., Marquard, M., Debois, S., Slaats, T. (2022).
   Decision Modelling in Timed Dynamic Condition Response Graphs with Data.
   BPM 2021 Workshops, LNBIP 436, pp. 362-374.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union


class DataType(Enum):
    """Types for events in a data-aware DCR graph (Definition 2, item ii)."""
    INT = 'int'
    BOOL = 'bool'
    VOID = 'void'


# ---------------------------------------------------------------------------
# Expression AST nodes
# ---------------------------------------------------------------------------

class Expression(ABC):
    """Base class for all expression AST nodes."""

    @abstractmethod
    def evaluate(self, event_values: Dict[str, Any],
                 registry: Optional[Dict[str, Callable]] = None) -> Any:
        """
        Evaluate the expression given a mapping from event ids to their current values.

        Parameters
        ----------
        event_values : Dict[str, Any]
            Mapping event_id -> value (int, bool, or None for void).
        registry : dict, optional
            Mapping from predicate name to callable, used by
            :class:`FunctionCallExpression` nodes.

        Returns
        -------
        Any
            The result of evaluating the expression.
        """
        pass

    @abstractmethod
    def __repr__(self) -> str:
        pass

    def __eq__(self, other):
        return isinstance(other, self.__class__) and repr(self) == repr(other)

    def __hash__(self):
        return hash(repr(self))


class VoidExpression(Expression):
    """The void expression, used for events without data."""

    def evaluate(self, event_values: Dict[str, Any],
                 registry: Optional[Dict[str, Callable]] = None) -> None:
        return None

    def __repr__(self):
        return 'void'


# ---------------------------------------------------------------------------
# Integer expressions (IExpE)
# ---------------------------------------------------------------------------

class IntConstant(Expression):
    """An integer constant ``n``."""

    def __init__(self, value: int):
        self.value = value

    def evaluate(self, event_values: Dict[str, Any],
                 registry: Optional[Dict[str, Callable]] = None) -> int:
        return self.value

    def __repr__(self):
        return str(self.value)


class EventRef(Expression):
    """
    A reference to an event's current value ``e``.

    Looks up the event's most-recently stored value in the marking.
    """

    def __init__(self, event_id: str):
        self.event_id = event_id

    def evaluate(self, event_values: Dict[str, Any],
                 registry: Optional[Dict[str, Callable]] = None) -> Any:
        if self.event_id not in event_values:
            raise ValueError(
                f"Event '{self.event_id}' has no value in the current marking. "
                "It may not have been executed yet."
            )
        return event_values[self.event_id]

    def __repr__(self):
        return f'Event({self.event_id})'


class BoolConstant(Expression):
    """A boolean constant ``b``."""

    def __init__(self, value: bool):
        self.value = value

    def evaluate(self, event_values: Dict[str, Any],
                 registry: Optional[Dict[str, Callable]] = None) -> bool:
        return self.value

    def __repr__(self):
        return str(self.value)


# ---------------------------------------------------------------------------
# Arithmetic operators (IOp: +, -, *)
# ---------------------------------------------------------------------------

class ArithOp(Enum):
    ADD = '+'
    SUB = '-'
    MUL = '*'


_ARITH_OPS = {
    ArithOp.ADD: lambda a, b: a + b,
    ArithOp.SUB: lambda a, b: a - b,
    ArithOp.MUL: lambda a, b: a * b,
}


class ArithExpression(Expression):
    """``IExpE IOp IExpE`` — an arithmetic binary operation on integers."""

    def __init__(self, left: Expression, op: ArithOp, right: Expression):
        self.left = left
        self.op = op
        self.right = right

    def evaluate(self, event_values: Dict[str, Any],
                 registry: Optional[Dict[str, Callable]] = None) -> int:
        left_val = self.left.evaluate(event_values, registry)
        right_val = self.right.evaluate(event_values, registry)
        return _ARITH_OPS[self.op](left_val, right_val)

    def __repr__(self):
        return f'({self.left} {self.op.value} {self.right})'


# ---------------------------------------------------------------------------
# Comparison operators (IBOp: =, <, >, <=, >=)
# ---------------------------------------------------------------------------

class CompOp(Enum):
    EQ = '='
    LT = '<'
    GT = '>'
    LE = '<='
    GE = '>='


_COMP_OPS = {
    CompOp.EQ: lambda a, b: a == b,
    CompOp.LT: lambda a, b: a < b,
    CompOp.GT: lambda a, b: a > b,
    CompOp.LE: lambda a, b: a <= b,
    CompOp.GE: lambda a, b: a >= b,
}


class CompExpression(Expression):
    """``IExpE IBOp IExpE`` — a comparison yielding a boolean."""

    def __init__(self, left: Expression, op: CompOp, right: Expression):
        self.left = left
        self.op = op
        self.right = right

    def evaluate(self, event_values: Dict[str, Any],
                 registry: Optional[Dict[str, Callable]] = None) -> bool:
        left_val = self.left.evaluate(event_values, registry)
        right_val = self.right.evaluate(event_values, registry)
        return _COMP_OPS[self.op](left_val, right_val)

    def __repr__(self):
        return f'({self.left} {self.op.value} {self.right})'


# ---------------------------------------------------------------------------
# Boolean operators (BOp: and, or) and not
# ---------------------------------------------------------------------------

class BoolOp(Enum):
    AND = 'and'
    OR = 'or'


_BOOL_OPS = {
    BoolOp.AND: lambda a, b: a and b,
    BoolOp.OR: lambda a, b: a or b,
}


class BoolBinaryExpression(Expression):
    """``BExpE BOp BExpE`` — a boolean binary operation."""

    def __init__(self, left: Expression, op: BoolOp, right: Expression):
        self.left = left
        self.op = op
        self.right = right

    def evaluate(self, event_values: Dict[str, Any],
                 registry: Optional[Dict[str, Callable]] = None) -> bool:
        left_val = self.left.evaluate(event_values, registry)
        right_val = self.right.evaluate(event_values, registry)
        return _BOOL_OPS[self.op](left_val, right_val)

    def __repr__(self):
        return f'({self.left} {self.op.value} {self.right})'


class NotExpression(Expression):
    """``not BExpE`` — boolean negation."""

    def __init__(self, operand: Expression):
        self.operand = operand

    def evaluate(self, event_values: Dict[str, Any],
                 registry: Optional[Dict[str, Callable]] = None) -> bool:
        return not self.operand.evaluate(event_values, registry)

    def __repr__(self):
        return f'(not {self.operand})'


class IfThenElseExpression(Expression):
    """``if BExpE then ExpE else ExpE`` — conditional expression."""

    def __init__(self, condition: Expression, then_expr: Expression, else_expr: Expression):
        self.condition = condition
        self.then_expr = then_expr
        self.else_expr = else_expr

    def evaluate(self, event_values: Dict[str, Any],
                 registry: Optional[Dict[str, Callable]] = None) -> Any:
        if self.condition.evaluate(event_values, registry):
            return self.then_expr.evaluate(event_values, registry)
        else:
            return self.else_expr.evaluate(event_values, registry)

    def __repr__(self):
        return f'(if {self.condition} then {self.then_expr} else {self.else_expr})'


class FunctionCallExpression(Expression):
    """
    ``name(arg1, arg2, ...)`` — a call to a user-supplied predicate function.

    The function is resolved by name from the *registry* dict at evaluation
    time.  If the registry is ``None`` or the name is not present, a
    ``KeyError`` is raised (which :class:`Guard`'s caller,
    :meth:`DataSemantics._evaluate_guard`, catches and converts to ``False``).

    Parameters
    ----------
    name : str
        Public Python identifier naming the predicate function.
    args : list of Expression
        Argument expressions, evaluated in order against ``event_values``
        and passed as positional arguments to the function.
    """

    def __init__(self, name: str, args: List[Expression]):
        self.name = name
        self.args = args

    def evaluate(self, event_values: Dict[str, Any],
                 registry: Optional[Dict[str, Callable]] = None) -> bool:
        if registry is None or self.name not in registry:
            raise KeyError(
                f"Predicate '{self.name}' not found in registry. "
                "Register it on DataDcrGraph.predicate_registry."
            )
        fn = registry[self.name]
        evaluated_args = [a.evaluate(event_values, registry) for a in self.args]
        return bool(fn(*evaluated_args))

    def __repr__(self):
        args_repr = ', '.join(repr(a) for a in self.args)
        return f'{self.name}({args_repr})'


# ---------------------------------------------------------------------------
# Input marker (D(e) = ?) — not an expression per se, but a sentinel
# ---------------------------------------------------------------------------

INPUT_MARKER = '?'


# ---------------------------------------------------------------------------
# Guard — a convenience wrapper for a boolean expression used on relations
# ---------------------------------------------------------------------------

class Guard:
    """
    A guard on a DCR relation.

    A guard wraps a boolean expression that is evaluated against the current
    event values in the marking. If no expression is provided, the guard is
    trivially true (equivalent to an unguarded relation).

    Parameters
    ----------
    expression : Expression, optional
        A boolean expression. If ``None``, the guard is always ``True``.
    """

    def __init__(self, expression: Optional[Expression] = None):
        self.expression = expression

    def evaluate(self, event_values: Dict[str, Any],
                 registry: Optional[Dict[str, Callable]] = None) -> bool:
        if self.expression is None:
            return True
        return bool(self.expression.evaluate(event_values, registry))

    @property
    def is_trivial(self) -> bool:
        """Returns True if the guard is always true (no expression)."""
        return self.expression is None

    def __repr__(self):
        if self.expression is None:
            return 'Guard(True)'
        return f'Guard({self.expression})'

    def __eq__(self, other):
        return isinstance(other, Guard) and self.expression == other.expression

    def __hash__(self):
        return hash(repr(self))


# ---------------------------------------------------------------------------
# Builder helpers for concise expression construction
# ---------------------------------------------------------------------------

def const(value: Union[int, bool]) -> Expression:
    """Create a constant expression from a Python value."""
    if isinstance(value, bool):
        return BoolConstant(value)
    elif isinstance(value, int):
        return IntConstant(value)
    raise TypeError(f"Unsupported constant type: {type(value)}")


def event_ref(event_id: str) -> EventRef:
    """Create an event reference expression."""
    return EventRef(event_id)


def eq(left: Expression, right: Expression) -> CompExpression:
    return CompExpression(left, CompOp.EQ, right)


def lt(left: Expression, right: Expression) -> CompExpression:
    return CompExpression(left, CompOp.LT, right)


def gt(left: Expression, right: Expression) -> CompExpression:
    return CompExpression(left, CompOp.GT, right)


def le(left: Expression, right: Expression) -> CompExpression:
    return CompExpression(left, CompOp.LE, right)


def ge(left: Expression, right: Expression) -> CompExpression:
    return CompExpression(left, CompOp.GE, right)


def add(left: Expression, right: Expression) -> ArithExpression:
    return ArithExpression(left, ArithOp.ADD, right)


def sub(left: Expression, right: Expression) -> ArithExpression:
    return ArithExpression(left, ArithOp.SUB, right)


def mul(left: Expression, right: Expression) -> ArithExpression:
    return ArithExpression(left, ArithOp.MUL, right)


def and_(left: Expression, right: Expression) -> BoolBinaryExpression:
    return BoolBinaryExpression(left, BoolOp.AND, right)


def or_(left: Expression, right: Expression) -> BoolBinaryExpression:
    return BoolBinaryExpression(left, BoolOp.OR, right)


def not_(operand: Expression) -> NotExpression:
    return NotExpression(operand)


def if_then_else(condition: Expression, then_expr: Expression, else_expr: Expression) -> IfThenElseExpression:
    return IfThenElseExpression(condition, then_expr, else_expr)
