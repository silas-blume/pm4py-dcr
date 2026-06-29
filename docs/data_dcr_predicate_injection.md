# Predicate Injection for Data-Aware DCR Guards

This document describes the predicate injection feature added to the data-aware
DCR graph layer.  It explains the motivation, design, the files that were
changed, and how to use the feature.

---

## 1. Motivation

The formal expression language for DCR guards (Definition 1 in [1]) covers
integer and boolean constants, event references, arithmetic, comparisons, and
boolean connectives.  This is sufficient for many process models, but
sometimes a guard condition requires logic that cannot be expressed in the
fixed grammar — e.g. checking whether a string value matches a pattern, or
computing a domain-specific score over event values.

The approach is inspired by *Declare4PyRM* [2], which injects user-supplied
Python callables into the constraint-evaluation globals of Declare conformance
checking.  The same idea is adapted here for DCR graphs: predicates are loaded
from a plain Python file, registered on the graph, and called inside the AST
evaluator.

---

## 2. Design

### 2.1 What is a predicate?

A predicate is any **public Python function that returns a bool** and accepts
one or more positional arguments.  Each argument corresponds to one
`[EventId]` expression evaluated against `marking.event_values`.

```python
# predicates.py

def high_value(amount):
    """True if the amount exceeds 1000."""
    return isinstance(amount, (int, float)) and amount > 1000

def same_category(cat_a, cat_b):
    """True if both events share the same category string."""
    return (isinstance(cat_a, str) and isinstance(cat_b, str)
            and cat_a.strip().lower() == cat_b.strip().lower())
```

### 2.2 How predicates are called in a guard

In a guard string (in Python code or in an XML `guard=""` attribute), a
predicate call looks exactly like a Python function call:

```
high_value([Amount])
same_category([CategoryA], [CategoryB])
```

The square-bracket syntax `[EventId]` is the existing DCR notation for an
event reference.  Arguments are evaluated against the current
`marking.event_values` and passed in order to the predicate function.

### 2.3 Data flow

```
Guard string (e.g. "high_value([Amount])")
    │
    ▼
parse_guard()                    ← expression_parser.py
    │  recognises IDENT '(' args ')'
    ▼
FunctionCallExpression(name="high_value", args=[EventRef("Amount")])
    │  stored as Guard.expression on a DataDcrGraph relation
    ▼
DataSemantics.enabled() / execute()
    │  calls _evaluate_guard(guard, event_values, graph.predicate_registry)
    ▼
Guard.evaluate(event_values, registry)
    │  delegates to FunctionCallExpression.evaluate(...)
    ▼
registry["high_value"](event_values["Amount"])
    │
    ▼
bool result  →  relation fires / is blocked
```

If the function name is absent from the registry (or the registry is `None`),
`FunctionCallExpression.evaluate` raises `KeyError`, which
`DataSemantics._evaluate_guard` catches and converts to `False` (the guard is
treated as inactive — same behaviour as a missing event value).

### 2.4 Relationship to formal DCR semantics

Guards are formally defined as boolean-valued expressions over event values.
Predicate functions are exactly that: they take one or more event values and
return a boolean.  The enabling and execution rules of Definition 3 / 4 in [1]
are unchanged — only the expression language is extended.

The one informal contract added is that predicates must be **pure and
deterministic** (no side effects, same result for same inputs).  This is the
same requirement that Declare4PyRM places on its predicates.

---

## 3. Files Changed

| File | Type | Summary |
|---|---|---|
| `pm4py/objects/dcr/data/predicate_loader.py` | **new** | Loads and validates predicates from a Python file; `load_predicates(path)` and `resolve_predicates(path, dict)` |
| `pm4py/objects/dcr/data/expressions.py` | modified | Added `FunctionCallExpression` AST node; threaded `registry=None` through all `evaluate()` signatures including `Guard.evaluate()` |
| `pm4py/objects/dcr/data/expression_parser.py` | modified | Added `IDENT` and `COMMA` token types; parser recognises `name(arg, …)` in guards; `serialize_expression` handles `FunctionCallExpression` |
| `pm4py/objects/dcr/data/obj.py` | modified | Added `predicate_registry: Dict[str, DataPredicate]` field to `DataDcrGraph` |
| `pm4py/objects/dcr/data/semantics.py` | modified | `_evaluate_guard` and `_apply_guarded_relation` accept `registry`; all call sites pass `graph.predicate_registry` |
| `pm4py/algo/conformance/dcr/rules/data_guard.py` | modified | Passes `graph.predicate_registry` to every `_evaluate_guard` call |
| `pm4py/algo/conformance/dcr/variants/classic.py` | modified | Added `Parameters.PREDICATE_FILE_PATH`; loads predicates onto the graph in `RuleBasedConformance.__init__` |

---

## 4. Usage

### 4.1 Programmatic setup (inline predicates)

```python
from pm4py.objects.dcr.data.obj import DataDcrGraph
from pm4py.objects.dcr.data.expression_parser import parse_guard
from pm4py.objects.dcr.data.semantics import DataSemantics

# Build a graph with a predicate guard
graph = DataDcrGraph()
graph.events = {'SubmitExpense', 'Approve'}
graph.marking.included = {'SubmitExpense', 'Approve'}

# Guarded condition: Approve is a condition for SubmitExpense
# but only when high_value([Approve]) is True
graph.guarded_conditions['SubmitExpense'] = {
    'Approve': parse_guard('high_value([Approve])')
}

# Register the predicate on the graph
graph.predicate_registry = {
    'high_value': lambda amount: isinstance(amount, (int, float)) and amount > 1000
}

sem = DataSemantics()
# Approve not yet executed → guard inactive → SubmitExpense is enabled
print(sem.enabled(graph))   # {'SubmitExpense', 'Approve'}

# Execute Approve with a high value → guard becomes True → SubmitExpense disabled
sem.execute(graph, 'Approve', input_value=2000)
print(sem.enabled(graph))   # {'SubmitExpense'}  ← still enabled because condition is now met
```

### 4.2 Loading predicates from a file

```python
from pm4py.objects.dcr.data.predicate_loader import load_predicates, resolve_predicates

# Load all public functions from a Python file
graph.predicate_registry = load_predicates("path/to/predicates.py")

# Or merge file predicates with inline functions
graph.predicate_registry = resolve_predicates(
    predicate_file_path="path/to/predicates.py",
    predicate_functions={"extra_check": lambda x: x > 0},
)
```

### 4.3 Conformance checking with a predicate file

Pass `predicate_file_path` as a parameter to `RuleBasedConformance`.  The
predicates are automatically loaded and attached to the graph before replay
begins.

```python
from pm4py.algo.conformance.dcr.variants.classic import RuleBasedConformance, Parameters

results = RuleBasedConformance(
    log=event_log,
    graph=graph,
    parameters={
        Parameters.PREDICATE_FILE_PATH.value: "path/to/predicates.py",
        Parameters.ACTIVITY_KEY.value: "concept:name",
    }
).apply_conformance()
```

### 4.4 Guard expressions in XML

Predicate calls are stored in XML `guard=""` attributes using the same string
syntax and round-trip cleanly:

```xml
<guardedConditions>
  <condition sourceId="Approve" targetId="SubmitExpense"
             guard="high_value([Approve])"/>
</guardedConditions>
```

The importer calls `parse_guard("high_value([Approve])")`, which produces a
`FunctionCallExpression` AST node.  On export, `serialize_expression` writes
`high_value([Approve])` back to the attribute.  The predicate registry is
**not** stored in XML — it must be supplied at runtime.

---

## 5. Writing predicates

Rules enforced by the predicate loader:

| Rule | Reason |
|---|---|
| Public identifier (no leading `_`) | Consistent with Python convention; private helpers are excluded |
| Callable | Must be a function or callable object |
| At least 1 required positional argument | Must accept the evaluated event values |
| No required keyword-only parameters | Simplifies call-site code |
| Defined in the loaded module (not imported) | Avoids accidentally capturing stdlib functions |

Example of a valid predicates file:

```python
# predicates.py

def above_threshold(value):
    return isinstance(value, (int, float)) and value > 500

def same_department(dept_a, dept_b):
    if not (isinstance(dept_a, str) and isinstance(dept_b, str)):
        return False
    return dept_a.strip().lower() == dept_b.strip().lower()

def within_budget(requested, budget):
    return isinstance(requested, (int, float)) and isinstance(budget, (int, float)) \
           and requested <= budget
```

---

## 6. Validation failures

`_evaluate_guard` returns `False` (guard inactive) for:

- Missing event value in `marking.event_values` (`ValueError` or `KeyError`)
- Predicate name not in registry (`KeyError` from `FunctionCallExpression`)
- Type error inside the predicate body (`TypeError`)

This matches the existing safe-evaluation contract for the built-in expression
types.

---

## References

[1] Hildebrandt, T.T., Normann, H., Marquard, M., Debois, S., Slaats, T. (2022).
*Decision Modelling in Timed Dynamic Condition Response Graphs with Data.*
BPM 2021 Workshops, LNBIP 436, pp. 362–374.

[2] Declare4PyRM (2024). Injectable predicate mechanism for Declare conformance
checking. `/home/silas/projects/Declare4PyRM/Declare4Py/Utils/Declare/predicate_loader.py`.
