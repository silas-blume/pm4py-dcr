"""
Expression string parser for data-aware DCR graphs.

Converts a human-readable expression string into an :class:`Expression` AST
instance (or ``INPUT_MARKER`` for input events) and vice versa
(:func:`serialize_expression`).

Expression String Syntax
------------------------
The syntax is designed to be readable in XML attribute values. Square brackets
are used for event references so that event IDs containing spaces or special
characters are unambiguous.

.. code-block:: text

    ?                           → input event (INPUT_MARKER)
    void                        → VoidExpression
    42                          → IntConstant(42)
    true / false                → BoolConstant(True / False)
    [EventId]                   → EventRef("EventId")
    [A] + [B]                   → ArithExpression(+)
    [A] - 5                     → ArithExpression(-)
    [A] * 2                     → ArithExpression(*)
    [A] == 2                    → CompExpression(==)
    [A] < 200                   → CompExpression(<)
    [A] > 0 and [B] == true     → BoolBinaryExpression(and)
    [A] > 0 or [B] == false     → BoolBinaryExpression(or)
    not ([A] == 1)              → NotExpression
    if [A] < 200 then 1 else 2  → IfThenElseExpression

Operator Precedence (lowest to highest)
-----------------------------------------
    if/then/else < or < and < not < comparison < + / - < * < atom

Parentheses can be used freely to override precedence.

Serialization
-------------
:func:`serialize_expression` produces the canonical string form that
:func:`parse_expression` can round-trip back to the original AST.

Notes
-----
- XML attribute values cannot contain raw ``<`` or ``&``; the surrounding XML
  serialiser (lxml) handles entity encoding automatically so you write ``<``
  in Python and lxml writes ``&lt;`` in the file.
- Event IDs inside ``[...]`` may contain any character except ``]``.
- Whitespace is insignificant outside ``[...]``.
"""

import re
from enum import Enum, auto
from typing import Any, Union

from pm4py.objects.dcr.data.expressions import (
    INPUT_MARKER,
    ArithExpression, ArithOp,
    BoolBinaryExpression, BoolOp,
    BoolConstant,
    CompExpression, CompOp,
    EventRef,
    Expression,
    FunctionCallExpression,
    Guard,
    IfThenElseExpression,
    IntConstant,
    NotExpression,
    VoidExpression,
)


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

class _TT(Enum):
    """Token types."""
    INT = auto()
    BOOL = auto()
    VOID = auto()
    QUESTION = auto()
    REF = auto()        # [EventId]
    PLUS = auto()
    MINUS = auto()
    MUL = auto()
    EQ = auto()         # ==
    LT = auto()         # <
    GT = auto()         # >
    LE = auto()         # <=
    GE = auto()         # >=
    AND = auto()
    OR = auto()
    NOT = auto()
    IF = auto()
    THEN = auto()
    ELSE = auto()
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    IDENT = auto()      # bare identifier — predicate function name
    EOF = auto()


_KEYWORDS = {
    'true': (_TT.BOOL, True),
    'false': (_TT.BOOL, False),
    'void': (_TT.VOID, None),
    'and': (_TT.AND, None),
    'or': (_TT.OR, None),
    'not': (_TT.NOT, None),
    'if': (_TT.IF, None),
    'then': (_TT.THEN, None),
    'else': (_TT.ELSE, None),
}


class _Token:
    __slots__ = ('type', 'value')

    def __init__(self, tt: _TT, value=None):
        self.type = tt
        self.value = value

    def __repr__(self):
        return f'Token({self.type}, {self.value!r})'


def _tokenize(s: str) -> list:
    """Convert an expression string into a list of tokens."""
    tokens = []
    i = 0
    n = len(s)

    while i < n:
        # Skip whitespace
        if s[i].isspace():
            i += 1
            continue

        # Special single-character symbols
        ch = s[i]

        # Event reference [EventId]
        if ch == '[':
            end = s.find(']', i + 1)
            if end == -1:
                raise ValueError(f"Unclosed '[' in expression at position {i}: {s!r}")
            event_id = s[i + 1:end]
            tokens.append(_Token(_TT.REF, event_id))
            i = end + 1
            continue

        if ch == '(':
            tokens.append(_Token(_TT.LPAREN))
            i += 1
            continue
        if ch == ')':
            tokens.append(_Token(_TT.RPAREN))
            i += 1
            continue
        if ch == '+':
            tokens.append(_Token(_TT.PLUS))
            i += 1
            continue
        if ch == '-':
            tokens.append(_Token(_TT.MINUS))
            i += 1
            continue
        if ch == '*':
            tokens.append(_Token(_TT.MUL))
            i += 1
            continue
        if ch == ',':
            tokens.append(_Token(_TT.COMMA))
            i += 1
            continue
        if ch == '?':
            tokens.append(_Token(_TT.QUESTION))
            i += 1
            continue

        # Two-char operators: ==, <=, >=
        two = s[i:i+2]
        if two == '==':
            tokens.append(_Token(_TT.EQ))
            i += 2
            continue
        if two == '<=':
            tokens.append(_Token(_TT.LE))
            i += 2
            continue
        if two == '>=':
            tokens.append(_Token(_TT.GE))
            i += 2
            continue

        # Single-char comparison
        if ch == '<':
            tokens.append(_Token(_TT.LT))
            i += 1
            continue
        if ch == '>':
            tokens.append(_Token(_TT.GT))
            i += 1
            continue

        # Integer literal
        if ch.isdigit() or (ch == '-' and i + 1 < n and s[i + 1].isdigit()):
            j = i + 1
            while j < n and s[j].isdigit():
                j += 1
            tokens.append(_Token(_TT.INT, int(s[i:j])))
            i = j
            continue

        # Keyword or identifier
        if ch.isalpha() or ch == '_':
            j = i + 1
            while j < n and (s[j].isalnum() or s[j] == '_'):
                j += 1
            word = s[i:j]
            kw = _KEYWORDS.get(word)
            if kw:
                tokens.append(_Token(kw[0], kw[1]))
            else:
                # Not a reserved keyword — treat as a predicate function name
                tokens.append(_Token(_TT.IDENT, word))
            i = j
            continue

        raise ValueError(f"Unexpected character {ch!r} at position {i} in expression: {s!r}")

    tokens.append(_Token(_TT.EOF))
    return tokens


# ---------------------------------------------------------------------------
# Recursive Descent Parser
# ---------------------------------------------------------------------------

class _Parser:
    """
    Recursive descent parser converting a token list into an Expression AST.

    Grammar (precedence lowest → highest):
        expr     := if_expr
        if_expr  := 'if' expr 'then' expr 'else' expr  |  or_expr
        or_expr  := and_expr ('or' and_expr)*
        and_expr := not_expr ('and' not_expr)*
        not_expr := 'not' not_expr  |  cmp_expr
        cmp_expr := add_expr (('=='|'<'|'>'|'<='|'>=') add_expr)?
        add_expr := mul_expr (('+' | '-') mul_expr)*
        mul_expr := atom ('*' atom)*
        atom     := '(' expr ')'  |  '[' event_id ']'  |  INT  |  BOOL  |  VOID
    """

    def __init__(self, tokens: list):
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _consume(self, expected: _TT = None) -> _Token:
        tok = self._tokens[self._pos]
        if expected is not None and tok.type != expected:
            raise ValueError(
                f"Expected {expected} but got {tok} at position {self._pos}"
            )
        self._pos += 1
        return tok

    def parse(self) -> Expression:
        expr = self._expr()
        self._consume(_TT.EOF)
        return expr

    def _expr(self) -> Expression:
        return self._if_expr()

    def _if_expr(self) -> Expression:
        if self._peek().type == _TT.IF:
            self._consume(_TT.IF)
            cond = self._expr()
            self._consume(_TT.THEN)
            then_expr = self._expr()
            self._consume(_TT.ELSE)
            else_expr = self._expr()
            return IfThenElseExpression(cond, then_expr, else_expr)
        return self._or_expr()

    def _or_expr(self) -> Expression:
        left = self._and_expr()
        while self._peek().type == _TT.OR:
            self._consume(_TT.OR)
            right = self._and_expr()
            left = BoolBinaryExpression(left, BoolOp.OR, right)
        return left

    def _and_expr(self) -> Expression:
        left = self._not_expr()
        while self._peek().type == _TT.AND:
            self._consume(_TT.AND)
            right = self._not_expr()
            left = BoolBinaryExpression(left, BoolOp.AND, right)
        return left

    def _not_expr(self) -> Expression:
        if self._peek().type == _TT.NOT:
            self._consume(_TT.NOT)
            return NotExpression(self._not_expr())
        return self._cmp_expr()

    _CMP_MAP = {
        _TT.EQ: CompOp.EQ,
        _TT.LT: CompOp.LT,
        _TT.GT: CompOp.GT,
        _TT.LE: CompOp.LE,
        _TT.GE: CompOp.GE,
    }

    def _cmp_expr(self) -> Expression:
        left = self._add_expr()
        tt = self._peek().type
        op = self._CMP_MAP.get(tt)
        if op is not None:
            self._consume(tt)
            right = self._add_expr()
            return CompExpression(left, op, right)
        return left

    def _add_expr(self) -> Expression:
        left = self._mul_expr()
        while self._peek().type in (_TT.PLUS, _TT.MINUS):
            op_tt = self._consume().type
            right = self._mul_expr()
            arith_op = ArithOp.ADD if op_tt == _TT.PLUS else ArithOp.SUB
            left = ArithExpression(left, arith_op, right)
        return left

    def _mul_expr(self) -> Expression:
        left = self._atom()
        while self._peek().type == _TT.MUL:
            self._consume(_TT.MUL)
            right = self._atom()
            left = ArithExpression(left, ArithOp.MUL, right)
        return left

    def _atom(self) -> Expression:
        tok = self._peek()
        match tok.type:
            case _TT.LPAREN:
                self._consume(_TT.LPAREN)
                expr = self._expr()
                self._consume(_TT.RPAREN)
                return expr
            case _TT.REF:
                self._consume(_TT.REF)
                return EventRef(tok.value)
            case _TT.INT:
                self._consume(_TT.INT)
                return IntConstant(tok.value)
            case _TT.BOOL:
                self._consume(_TT.BOOL)
                return BoolConstant(tok.value)
            case _TT.VOID:
                self._consume(_TT.VOID)
                return VoidExpression()
            case _TT.IDENT:
                # Predicate function call: name '(' [expr (',' expr)*] ')'
                name = self._consume(_TT.IDENT).value
                self._consume(_TT.LPAREN)
                args = []
                if self._peek().type != _TT.RPAREN:
                    args.append(self._expr())
                    while self._peek().type == _TT.COMMA:
                        self._consume(_TT.COMMA)
                        args.append(self._expr())
                self._consume(_TT.RPAREN)
                return FunctionCallExpression(name, args)
            case _:
                raise ValueError(
                    f"Unexpected token {tok} at position {self._pos} — "
                    "expected an expression atom"
                )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_expression(s: str) -> Union[Expression, str]:
    """
    Parse an expression string into an :class:`Expression` AST node.

    Parameters
    ----------
    s : str
        The expression string.  Special values:

        * ``"?"``   → returns :data:`~pm4py.objects.dcr.data.expressions.INPUT_MARKER`
        * ``"void"`` → returns :class:`~pm4py.objects.dcr.data.expressions.VoidExpression`

    Returns
    -------
    Expression or str
        An ``Expression`` instance, or ``INPUT_MARKER`` (``'?'``) for input events.

    Raises
    ------
    ValueError
        If the string cannot be parsed as a valid expression.

    Examples
    --------
    >>> parse_expression("?")
    '?'
    >>> parse_expression("42")
    42
    >>> parse_expression("if [Amount] < 200 then 1 else 2")
    ((Amount < 200) ? 1 : 2)
    """
    s = s.strip()
    if s == INPUT_MARKER:
        return INPUT_MARKER
    tokens = _tokenize(s)
    return _Parser(tokens).parse()


def parse_guard(s: str) -> Guard:
    """
    Parse an expression string into a :class:`Guard`.

    An empty or whitespace-only string returns a trivial (always-true)
    :class:`Guard`.

    Parameters
    ----------
    s : str
        The guard expression string, or ``""`` for a trivial guard.

    Returns
    -------
    Guard
    """
    s = s.strip()
    if not s:
        return Guard()
    expr = parse_expression(s)
    if isinstance(expr, str):   # INPUT_MARKER — not valid as a guard
        raise ValueError(f"'?' is not a valid guard expression; guards must be boolean expressions")
    return Guard(expr)


def serialize_expression(expr: Union[Expression, str]) -> str:
    """
    Convert an :class:`Expression` AST (or ``INPUT_MARKER``) to its canonical
    string representation, suitable for embedding in an XML attribute value.

    The output is guaranteed to round-trip through :func:`parse_expression`.

    Parameters
    ----------
    expr : Expression or str
        The expression or ``INPUT_MARKER``.

    Returns
    -------
    str
        The expression string.

    Examples
    --------
    >>> from pm4py.objects.dcr.data.expressions import const, event_ref, lt, if_then_else
    >>> serialize_expression(if_then_else(lt(event_ref('Amount'), const(200)), const(1), const(2)))
    'if [Amount] < 200 then 1 else 2'
    """
    if expr == INPUT_MARKER:
        return INPUT_MARKER

    match expr:
        case VoidExpression():
            return 'void'
        case IntConstant():
            return str(expr.value)
        case BoolConstant():
            return 'true' if expr.value else 'false'
        case EventRef():
            return f'[{expr.event_id}]'
        case ArithExpression():
            op = {ArithOp.ADD: '+', ArithOp.SUB: '-', ArithOp.MUL: '*'}[expr.op]
            return f'({serialize_expression(expr.left)} {op} {serialize_expression(expr.right)})'
        case CompExpression():
            op = {
                CompOp.EQ: '==', CompOp.LT: '<', CompOp.GT: '>',
                CompOp.LE: '<=', CompOp.GE: '>=',
            }[expr.op]
            return f'({serialize_expression(expr.left)} {op} {serialize_expression(expr.right)})'
        case BoolBinaryExpression():
            op = {BoolOp.AND: 'and', BoolOp.OR: 'or'}[expr.op]
            return f'({serialize_expression(expr.left)} {op} {serialize_expression(expr.right)})'
        case NotExpression():
            return f'(not {serialize_expression(expr.operand)})'
        case IfThenElseExpression():
            cond = serialize_expression(expr.condition)
            then = serialize_expression(expr.then_expr)
            else_ = serialize_expression(expr.else_expr)
            return f'if {cond} then {then} else {else_}'
        case FunctionCallExpression():
            args_str = ', '.join(serialize_expression(a) for a in expr.args)
            return f'{expr.name}({args_str})'
        case _:
            raise TypeError(f"Cannot serialise expression of type {type(expr).__name__}")


def serialize_guard(guard: Guard) -> str:
    """
    Convert a :class:`Guard` to its string representation.

    A trivial guard (no expression) returns ``""``; a non-trivial guard
    returns the serialisation of its expression.

    Parameters
    ----------
    guard : Guard

    Returns
    -------
    str
    """
    if guard.is_trivial:
        return ''
    return serialize_expression(guard.expression)
