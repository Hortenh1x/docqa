"""Cross-field rules as small Python-like expressions, evaluated over a whitelist.

Examples: ``total == subtotal + tax``, ``abs(sum(line_amounts) - total) < 0.01``,
``end_date >= start_date``, ``len(parties) >= 2``. Names are field names; a rule whose
operands are missing (None) is *unknown*, not failed.
"""

import ast
from collections.abc import Callable
from typing import Any

_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "sum": lambda xs: sum(float(x) for x in (xs or []) if x is not None),
    "len": lambda xs: len(xs or []),
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
}
_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Constant,
    ast.Call,
    ast.List,
    ast.Tuple,
    ast.Load,
    ast.And,
    ast.Or,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
)
_MAX_RULE_CHARS = 300


class RuleUnknown(Exception):
    """An operand was missing — the rule cannot be decided."""


def compile_rule(expression: str, field_names: set[str]) -> ast.Expression:
    if len(expression) > _MAX_RULE_CHARS:
        raise ValueError("rule is too long")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"rule is not a valid expression: {exc.msg}") from None
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"rule uses unsupported syntax: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
                raise ValueError("rule calls an unknown function")
            if node.keywords:
                raise ValueError("rule functions take positional arguments only")
        if isinstance(node, ast.Name) and node.id not in _FUNCTIONS and node.id not in field_names:
            raise ValueError(f"rule references unknown field '{node.id}'")
        if isinstance(node, ast.Constant) and not isinstance(
            node.value, int | float | str | bool | type(None)
        ):
            raise ValueError("rule uses an unsupported constant")
    return tree


def evaluate_rule(tree: ast.Expression, values: dict[str, Any]) -> bool:
    """True/False, or RuleUnknown when a referenced value is None."""

    def ev(node: ast.AST) -> Any:
        match node:
            case ast.Expression(body=body):
                return ev(body)
            case ast.Constant(value=value):
                return value
            case ast.Name(id=name):
                if name in _FUNCTIONS:
                    return _FUNCTIONS[name]
                value = values.get(name)
                if value is None:
                    raise RuleUnknown(name)
                return value
            case ast.List(elts=elts) | ast.Tuple(elts=elts):
                return [ev(e) for e in elts]
            case ast.UnaryOp(op=ast.Not(), operand=operand):
                return not ev(operand)
            case ast.UnaryOp(op=ast.USub(), operand=operand):
                return -_num(ev(operand))
            case ast.UnaryOp(op=ast.UAdd(), operand=operand):
                return _num(ev(operand))
            case ast.BoolOp(op=ast.And(), values=parts):
                return all(bool(ev(p)) for p in parts)
            case ast.BoolOp(op=ast.Or(), values=parts):
                return any(bool(ev(p)) for p in parts)
            case ast.BinOp(left=left, op=op, right=right):
                a, b = ev(left), ev(right)
                if isinstance(op, ast.Add) and isinstance(a, str) and isinstance(b, str):
                    return a + b
                a, b = _num(a), _num(b)
                match op:
                    case ast.Add():
                        return a + b
                    case ast.Sub():
                        return a - b
                    case ast.Mult():
                        return a * b
                    case ast.Div():
                        return a / b if b else float("inf")
                    case ast.Mod():
                        return a % b if b else float("nan")
            case ast.Compare(left=left, ops=ops, comparators=comparators):
                current = ev(left)
                for cmp_op, comparator in zip(ops, comparators, strict=True):
                    other = ev(comparator)
                    if not _compare(cmp_op, current, other):
                        return False
                    current = other
                return True
            case ast.Call(func=ast.Name(id=name), args=args):
                return _FUNCTIONS[name](*[ev(a) for a in args])
        raise ValueError(f"unsupported node {type(node).__name__}")

    return bool(ev(tree))


def _num(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            raise RuleUnknown(value) from None
    raise RuleUnknown(str(value))


def _compare(op: ast.cmpop, a: Any, b: Any) -> bool:
    match op:
        case ast.In():
            return a in (b or [])
        case ast.NotIn():
            return a not in (b or [])
    if isinstance(a, str) and isinstance(b, str):
        pass  # ISO dates and plain strings compare lexicographically
    elif isinstance(a, list) or isinstance(b, list):
        pass
    else:
        a, b = _num(a), _num(b)
    match op:
        case ast.Eq():
            return bool(a == b)
        case ast.NotEq():
            return bool(a != b)
        case ast.Lt():
            return bool(a < b)
        case ast.LtE():
            return bool(a <= b)
        case ast.Gt():
            return bool(a > b)
        case ast.GtE():
            return bool(a >= b)
    raise ValueError("unsupported comparison")
