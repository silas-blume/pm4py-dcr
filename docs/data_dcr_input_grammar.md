# Data DCR Input Grammar (PM4Py-DCR)

This document specifies the accepted input grammar for *data-aware DCR* in this repository, based on `DataDcrGraph`, `DataSemantics`, and expression classes.

Key fact:
- There is currently no dedicated XML/JSON parser for data-aware DCR fields.
- Data-aware models are provided as Python objects/templates.

This document is designed to be directly usable for LLM-based generation.

## 1. Input Channels

Accepted ways to create data DCR inputs:

1. Construct `DataDcrGraph()` and assign fields programmatically.
2. Construct `DataDcrGraph(template_dict)` where `template_dict` uses the DCR template keys.
3. Use a DCR template dictionary and pass it through `cast_to_dcr_object(...)`.
   - If any data keys are non-empty, this returns `DataDcrGraph`.

Data keys that trigger data-aware casting:
- `eventTypes`
- `decisions`
- `guardedConditions`
- `guardedResponses`
- `guardedIncludes`
- `guardedExcludes`
- `guardedMilestones`
- `guardedNoResponses`

## 2. Canonical Template Schema

Data DCR extends the base `dcr_template` dictionary.

### 2.1 Root-Level Keys

```ebnf
DataDcrTemplate = {
  events: Set<EventId>,
  conditionsFor: Dict<EventId, Set<EventId>>,
  milestonesFor: Dict<EventId, Set<EventId>>,
  responseTo: Dict<EventId, Set<EventId>>,
  noResponseTo: Dict<EventId, Set<EventId>>,
  includesTo: Dict<EventId, Set<EventId>>,
  excludesTo: Dict<EventId, Set<EventId>>,

  marking: {
    executed: Set<EventId>,
    included: Set<EventId>,
    pending: Set<EventId>,
    executedTime: Dict<EventId, TimeValue>,
    pendingDeadline: Dict<EventId, TimeValue>,
    eventValues: Dict<EventId, Value>
  },

  conditionsForDelays: Dict<EventId, Dict<EventId, DurationValue>>,
  responseToDeadlines: Dict<EventId, Dict<EventId, DurationValue>>,

  subprocesses: Dict<GroupId, Set<EventId>>,
  nestedgroups: Dict<GroupId, Set<EventId>>,
  nestedgroupsMap: Dict<EventId, GroupId>,

  labels: Set<LabelId>,
  labelMapping: Dict<EventId, LabelId>,

  roles: Set<RoleId>,
  principals: Set<PrincipalId>,
  roleAssignments: Dict<RoleId, Set<EventId>>,
  readRoleAssignments: Dict<RoleId, Set<EventId>>,
  principalsAssignments: Dict<PrincipalId, Set<EventId>>,

  eventTypes: Dict<EventId, DataTypeNameOrEnum>,
  decisions: Dict<EventId, DecisionSpec>,

  guardedConditions: Dict<TargetEventId, Dict<SourceEventId, Guard>>,
  guardedResponses: Dict<SourceEventId, Dict<TargetEventId, Guard>>,
  guardedIncludes: Dict<SourceEventId, Dict<TargetEventId, Guard>>,
  guardedExcludes: Dict<SourceEventId, Dict<TargetEventId, Guard>>,
  guardedMilestones: Dict<TargetEventId, Dict<SourceEventId, Guard>>,
  guardedNoResponses: Dict<SourceEventId, Dict<TargetEventId, Guard>>
}
```

### 2.2 Value Domains

`DataTypeNameOrEnum`:
- `"int"`, `"bool"`, `"void"`, or `DataType.INT`, `DataType.BOOL`, `DataType.VOID`.

`DecisionSpec`:
- Input marker: `'?'` (`INPUT_MARKER`)
- Or an `Expression` instance

`Value`:
- `int` for int-typed events
- `bool` for bool-typed events
- `None` for void-typed events

`Guard`:
- `Guard()` for always-true
- `Guard(Expression)` for guarded relations

## 3. Expression Grammar (Decision and Guard Expressions)

The repository implements the expression grammar in `pm4py/objects/dcr/data/expressions.py`.

```ebnf
ExpE   = BExpE | IExpE | "void" ;

BExpE  = EventRefBool
       | BoolLiteral
       | IExpE IBOp IExpE
       | BExpE BOp BExpE
       | "not" BExpE
       | "if" BExpE "then" BExpE "else" BExpE ;

IExpE  = EventRefInt
       | IntLiteral
       | IExpE IOp IExpE
       | "if" BExpE "then" IExpE "else" IExpE ;

IBOp   = "=" | "<" | ">" | "<=" | ">=" ;
IOp    = "+" | "-" | "*" ;
BOp    = "and" | "or" ;
```

Runtime representation is an AST of Python classes:
- `IntConstant`, `BoolConstant`, `VoidExpression`, `EventRef`
- `ArithExpression`, `CompExpression`, `BoolBinaryExpression`, `NotExpression`, `IfThenElseExpression`
- `Guard`

Builder helpers (preferred for generation):
- Constants/refs: `const(v)`, `event_ref("E")`
- Comparisons: `eq`, `lt`, `gt`, `le`, `ge`
- Arithmetic: `add`, `sub`, `mul`
- Boolean: `and_`, `or_`, `not_`
- Conditional: `if_then_else(cond, then_expr, else_expr)`

## 4. Orientation of Relations (Critical for Correct Generation)

Unguarded and guarded relations do not all use the same key orientation.

Condition-like orientation (target -> {source -> ...}):
- `conditionsFor`
- `milestonesFor`
- `guardedConditions`
- `guardedMilestones`

Response/include/exclude/noresponse orientation (source -> {target -> ...}):
- `responseTo`
- `includesTo`
- `excludesTo`
- `noResponseTo`
- `guardedResponses`
- `guardedIncludes`
- `guardedExcludes`
- `guardedNoResponses`

## 5. Minimal Valid Data DCR Example (Programmatic)

```python
from pm4py.objects.dcr.data.expressions import (
    DataType, Guard, INPUT_MARKER, VoidExpression,
    const, event_ref, eq, lt, if_then_else,
)
from pm4py.objects.dcr.data.obj import DataDcrGraph

g = DataDcrGraph()
g.events = {"Amount", "Submit", "Decision"}
g.labels = {"Amount", "Submit", "Decision"}
g.label_map = {e: e for e in g.events}
g.marking.included = {"Amount", "Submit", "Decision"}

g.event_types = {
    "Amount": DataType.INT,
    "Submit": DataType.VOID,
    "Decision": DataType.INT,
}

g.decisions = {
    "Amount": INPUT_MARKER,
    "Submit": VoidExpression(),
    "Decision": if_then_else(
        lt(event_ref("Amount"), const(200)),
        const(1),
        const(2),
    ),
}

g.conditions = {"Submit": {"Amount"}}
g.responses = {"Submit": {"Decision"}}

g.guarded_responses = {
    "Decision": {
        "Submit": Guard(eq(event_ref("Decision"), const(2)))
    }
}
```

## 6. LLM Generation Contract

Use this contract to generate valid data DCR inputs:

1. Always define `events`, `labels`, and `label_map` consistently.
2. Assign `marking.included` explicitly.
3. Define `event_types` for each data-aware event.
4. Define `decisions` for each event that is data-relevant:
   - Input events: `INPUT_MARKER` (`'?'`)
   - Computed events: `Expression`
   - Void events: commonly `VoidExpression()`
5. Use `Guard(...)` objects for all guarded relation payloads.
6. Respect relation orientation from Section 4.
7. Ensure any event referenced in an expression has a value before evaluation at runtime.

## 7. Validation Constraints and Runtime Notes

There is little upfront schema validation in constructors. Most errors surface at execution time.

Important runtime implications:

1. `EventRef("X")` raises if `X` has no value in current marking.
2. Guard evaluation in semantics is fail-safe:
   - missing/invalid values lead to guard treated as false in semantic checks.
3. `is_input_event(e)` checks `decisions[e] == '?'`.
4. `is_decision_event(e)` requires `decisions[e]` to be an `Expression` instance.

## 8. What Is Not Supported as Data Input (Currently)

Not currently implemented in this repository:

1. Dedicated XML importer that parses `eventTypes`, `decisions`, and guarded relations.
2. Text parser for expression strings into AST nodes.
3. Native JSON schema deserializer for data DCR expressions.

So the authoritative data input format is the Python object/template form above.

## 9. Source of Truth (Code)

- `pm4py/objects/dcr/data/obj.py`
- `pm4py/objects/dcr/data/expressions.py`
- `pm4py/objects/dcr/data/semantics.py`
- `pm4py/objects/dcr/obj.py`
- `pm4py/objects/dcr/utils/utils.py`
- `tests/dcr_data_test.py`
- `examples/dcr_data_examples.py`
