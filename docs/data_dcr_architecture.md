# Data-Aware DCR Graphs — Architecture & Design

This document explains the architecture, concepts, and data flow of the
data-aware DCR graph extension implemented in PM4Py-DCR.  The implementation
follows the formalisation presented in:

> Hildebrandt, T.T., Normann, H., Marquard, M., Debois, S., Slaats, T. (2022).
> *Decision Modelling in Timed Dynamic Condition Response Graphs with Data.*
> BPM 2021 Workshops, LNBIP 436, pp. 362–374.

---

## 1. Class Hierarchy

The data-aware layer builds on top of the existing PM4Py DCR class hierarchy.
Each layer adds a specific set of features.

```mermaid
classDiagram
    direction TB

    class DcrGraph {
        events : Set
        marking : Marking
        conditions : Dict
        responses : Dict
        includes : Dict
        excludes : Dict
    }

    class DistributedDcrGraph {
        roles : Dict
        principals : Dict
    }

    class ExtendedDcrGraph {
        milestones : Dict
        noresponses : Dict
    }

    class HierarchicalDcrGraph {
        nestedgroups : Dict
    }

    class TimedDcrGraph {
        timedconditions : Dict
        timedresponses : Dict
    }

    class DataDcrGraph {
        event_types : Dict~str, DataType~
        decisions : Dict~str, Expression | '?'~
        guarded_conditions : Dict
        guarded_responses : Dict
        guarded_includes : Dict
        guarded_excludes : Dict
        guarded_milestones : Dict
        guarded_noresponses : Dict
    }

    DcrGraph <|-- DistributedDcrGraph
    DistributedDcrGraph <|-- ExtendedDcrGraph
    ExtendedDcrGraph <|-- HierarchicalDcrGraph
    HierarchicalDcrGraph <|-- TimedDcrGraph
    TimedDcrGraph <|-- DataDcrGraph
```

### Marking Hierarchy

The marking (runtime state of the graph) mirrors the class hierarchy:

```mermaid
classDiagram
    direction LR

    class Marking {
        executed : Set~str~
        included : Set~str~
        pending : Set~str~
    }

    class TimedMarking {
        executed_time : Dict
        pending_deadline : Dict
    }

    class DataMarking {
        event_values : Dict~str, Any~
        +reset(initial_marking)
    }

    Marking <|-- TimedMarking
    TimedMarking <|-- DataMarking
```

`DataMarking.event_values` stores the most recently produced value for each
executed event (e.g. `{'Amount': 800, 'Decision': 2}`).

---

## 2. Expression System (Definition 1)

Values in data-aware DCR graphs are integers or booleans.  Expressions form
an Abstract Syntax Tree (AST) that can be evaluated given the current event
values in the marking.

```mermaid
classDiagram
    direction TB

    class Expression {
        <<abstract>>
        +evaluate(event_values) Any
    }

    class VoidExpression {
        +evaluate() None
    }

    class IntConstant {
        value : int
        +evaluate() int
    }

    class BoolConstant {
        value : bool
        +evaluate() bool
    }

    class EventRef {
        event_id : str
        +evaluate() Any
    }

    class ArithExpression {
        left : Expression
        op : ArithOp
        right : Expression
        +evaluate() int
    }

    class CompExpression {
        left : Expression
        op : CompOp
        right : Expression
        +evaluate() bool
    }

    class BoolBinaryExpression {
        left : Expression
        op : BoolOp
        right : Expression
        +evaluate() bool
    }

    class NotExpression {
        operand : Expression
        +evaluate() bool
    }

    class IfThenElseExpression {
        condition : Expression
        then_expr : Expression
        else_expr : Expression
        +evaluate() Any
    }

    class Guard {
        expression : Expression | None
        +is_trivial : bool
        +evaluate() bool
    }

    Expression <|-- VoidExpression
    Expression <|-- IntConstant
    Expression <|-- BoolConstant
    Expression <|-- EventRef
    Expression <|-- ArithExpression
    Expression <|-- CompExpression
    Expression <|-- BoolBinaryExpression
    Expression <|-- NotExpression
    Expression <|-- IfThenElseExpression
    Guard o-- Expression : wraps
```

### Operator Enums

| Enum | Values | Domain |
|------|--------|--------|
| `ArithOp` | `ADD (+)`, `SUB (-)`, `MUL (*)` | int × int → int |
| `CompOp` | `EQ (==)`, `LT (<)`, `GT (>)`, `LE (<=)`, `GE (>=)` | int × int → bool |
| `BoolOp` | `AND (∧)`, `OR (∨)` | bool × bool → bool |

### Example: Decision Expression from the Paper

The expense report decision function uses a nested if-then-else:

```mermaid
graph TD
    R["Decision Expression"]
    C1{"Amount < 200?"}
    V1["1 (auto-approve)"]
    C2{"Amount ≥ 200 ∧ Type = 2?"}
    V2["2 (needs approval)"]
    C3{"Amount ≥ 5000 ∧ Type = 1?"}
    V3["3 (reject)"]
    V4["2 (needs approval)"]

    R --> C1
    C1 -->|true| V1
    C1 -->|false| C2
    C2 -->|true| V2
    C2 -->|false| C3
    C3 -->|true| V3
    C3 -->|false| V4

    style V1 fill:#4caf50,color:#fff
    style V2 fill:#ff9800,color:#fff
    style V3 fill:#f44336,color:#fff
    style V4 fill:#ff9800,color:#fff
```

---

## 3. Event Classification (Definition 2)

Every event in a data-aware DCR graph has a **type** and a **decision function**:

```mermaid
graph LR
    subgraph "Event Classification"
        direction TB
        E["Event e"]
        T{"Type(e)"}
        D{"Decision(e)"}

        E --> T
        E --> D

        T -->|Int| TI["Integer-valued"]
        T -->|Bool| TB["Boolean-valued"]
        T -->|Void| TV["No value"]

        D -->|"'?'"| DI["Input Event<br/>Value from environment"]
        D -->|Expression| DD["Decision Event<br/>Value computed from AST"]
    end

    style DI fill:#2196f3,color:#fff
    style DD fill:#9c27b0,color:#fff
    style TV fill:#607d8b,color:#fff
```

- **Input events** (`D(e) = ?`): receive their value from the event log or
  user at execution time.
- **Decision events** (`D(e) = expr`): compute their value by evaluating
  the expression over current event values in the marking.

---

## 4. Guarded Relations

Standard DCR relations (condition, response, include, exclude, milestone,
no-response) are always active.  **Guarded relations** carry a boolean guard
expression and only take effect when the guard evaluates to `true`.

```mermaid
graph LR
    subgraph "Guarded Relation"
        S["Source e'"] -->|"guard g"| T["Target e"]
    end

    subgraph "Evaluation"
        G{"g.evaluate(values)"}
        G -->|true| A["Relation ACTIVE<br/>Effect applied"]
        G -->|false| I["Relation INACTIVE<br/>No effect"]
        G -->|error| I2["Relation INACTIVE<br/>(missing values)"]
    end

    style A fill:#4caf50,color:#fff
    style I fill:#9e9e9e,color:#fff
    style I2 fill:#9e9e9e,color:#fff
```

### All Six Guarded Relation Types

```mermaid
graph TB
    subgraph "Blocking Relations (checked at enabling)"
        GC["Guarded Condition<br/>e' →[g] e<br/><i>If g is true, e' must be<br/>executed before e</i>"]
        GM["Guarded Milestone<br/>e' →[g] e<br/><i>If g is true, e' must not<br/>be pending for e to fire</i>"]
    end

    subgraph "Effect Relations (applied at execution)"
        GR["Guarded Response<br/>e →[g] e'<br/><i>If g is true, make e'<br/>pending</i>"]
        GNR["Guarded No-Response<br/>e →[g] e'<br/><i>If g is true, remove e'<br/>from pending</i>"]
        GI["Guarded Include<br/>e →[g] e'<br/><i>If g is true, include e'</i>"]
        GE["Guarded Exclude<br/>e →[g] e'<br/><i>If g is true, exclude e'</i>"]
    end

    style GC fill:#e3f2fd
    style GM fill:#e3f2fd
    style GR fill:#fff3e0
    style GNR fill:#fff3e0
    style GI fill:#e8f5e9
    style GE fill:#fce4ec
```

---

## 5. Enabling Semantics (Definition 3)

The enabling check determines which events can fire in the current marking:

```mermaid
flowchart TD
    Start["Is event e enabled?"] --> Inc{"e ∈ Included?"}
    Inc -->|No| Disabled["❌ DISABLED"]
    Inc -->|Yes| Cond

    subgraph "Unguarded Conditions"
        Cond{"∀ included source e'<br/>with condition → e:<br/>e' ∈ Executed?"}
    end
    Cond -->|No| Disabled

    subgraph "Guarded Conditions"
        Cond -->|Yes| GCond{"∀ (e' →[g] e) where<br/>e' included:<br/>if g=true, e' ∈ Executed?"}
    end
    GCond -->|No| Disabled

    subgraph "Unguarded Milestones"
        GCond -->|Yes| Mile{"∀ included source e'<br/>with milestone → e:<br/>e' ∉ Pending?"}
    end
    Mile -->|No| Disabled

    subgraph "Guarded Milestones"
        Mile -->|Yes| GMile{"∀ (e' →[g] e) where<br/>e' included:<br/>if g=true, e' ∉ Pending?"}
    end
    GMile -->|No| Disabled
    GMile -->|Yes| Enabled["✅ ENABLED"]

    style Disabled fill:#f44336,color:#fff
    style Enabled fill:#4caf50,color:#fff
```

**Guard evaluation failure** (missing event values, type errors) is treated
as `guard = false`, making the relation inactive.  This ensures that guards
referencing events that haven't been executed yet don't spuriously block.

---

## 6. Execution Semantics (Definition 4)

When an enabled event fires, the marking is updated in a specific order:

```mermaid
flowchart TD
    Fire["Execute event e"] --> Value

    subgraph "1. Compute Value"
        Value{"Decision(e)?"}
        Value -->|"'?'"| Input["Use input_value<br/>from environment"]
        Value -->|Expression| Eval["Evaluate expr<br/>over event_values"]
        Value -->|Void/None| NoVal["value = None"]
    end

    Input --> Update
    Eval --> Update
    NoVal --> Update

    subgraph "2. Update Marking"
        Update["pending.discard(e)<br/>executed.add(e)<br/>event_values[e] = value"]
    end

    Update --> NR

    subgraph "3. Apply No-Response"
        NR["Unguarded: pending.discard(e')<br/>Guarded: if g=true, pending.discard(e')"]
    end

    NR --> Excl

    subgraph "4. Apply Excludes"
        Excl["Unguarded: included.discard(e')<br/>Guarded: if g=true, included.discard(e')"]
    end

    Excl --> Incl

    subgraph "5. Apply Includes"
        Incl["Unguarded: included.add(e')<br/>Guarded: if g=true, included.add(e')"]
    end

    Incl --> Resp

    subgraph "6. Apply Responses"
        Resp["Unguarded: pending.add(e')<br/>Guarded: if g=true, pending.add(e')"]
    end

    Resp --> Done["Marking updated ✓"]

    style Fire fill:#2196f3,color:#fff
    style Done fill:#4caf50,color:#fff
```

The order **no-response → exclude → include → response** is semantically
significant.  For example, a no-response may remove a pending obligation
before a response re-adds it (or vice versa).

---

## 7. Semantics Class Hierarchy

```mermaid
classDiagram
    direction TB

    class DcrSemantics {
        +enabled(graph) Set~str~
        +execute(graph, event)
        +is_accepting(graph) bool
        +is_enabled(event, graph) bool
    }

    class ExtendedSemantics {
        +enabled(graph) Set~str~
        +execute(graph, event)
    }

    class DataSemantics {
        +enabled(graph) Set~str~
        +execute(graph, event, input_value)
        +is_accepting(graph) bool
        +get_event_values(graph) Dict
        -_evaluate_guard(guard, values)$ bool
        -_apply_guarded_relation(event, map, values, target_set, action)
    }

    DcrSemantics <|-- ExtendedSemantics
    ExtendedSemantics <|-- DataSemantics

    note for DataSemantics "Falls back to DcrSemantics\nfor non-DataDcrGraph instances\n(avoids AttributeError on milestones)"
```

`DataSemantics` uses two key helper methods to avoid duplicated code:

- **`_evaluate_guard(guard, values)`** — safely evaluates a guard, returning
  `False` on `ValueError`, `KeyError`, or `TypeError`.
- **`_apply_guarded_relation(event, map, values, target_set, action)`** —
  iterates over a guarded relation dict and applies `add` or `discard`
  to the marking set for each guard that evaluates to `true`.

---

## 8. Conformance Checking Pipeline

Conformance checking uses the **decorator pattern** to layer data-aware
checks on top of the standard rule-based checker:

```mermaid
flowchart LR
    subgraph "Checker Chain (Decorator Pattern)"
        direction TB
        DC["DataConstraintDecorator"]
        RC["RoleDecorator<br/>(if roles present)"]
        CC["ConcreteChecker"]

        DC -->|delegates to| RC
        RC -->|delegates to| CC
    end

    subgraph "Check Points"
        direction TB
        EN["enabled_checker()<br/>Condition + Milestone violations"]
        AL["all_checker()<br/>Extract input values from log"]
        AC["accepting_checker()<br/>Response violations"]
    end

    DC --- EN
    DC --- AL
    DC --- AC

    style DC fill:#9c27b0,color:#fff
    style RC fill:#3f51b5,color:#fff
    style CC fill:#009688,color:#fff
```

### DataConstraintDecorator Flow

```mermaid
flowchart TD
    subgraph "enabled_checker(event)"
        E1["1. Call base enabled_checker"]
        E2["2. CheckDataGuard.check_enabled_rule()"]
        E3{"Guarded condition<br/>active & source<br/>not executed?"}
        E4["Add dataConditionViolation"]
        E5{"Guarded milestone<br/>active & source<br/>pending?"}
        E6["Add dataMilestoneViolation"]

        E1 --> E2 --> E3
        E3 -->|Yes| E4
        E3 -->|No| E5
        E5 -->|Yes| E6
    end

    subgraph "all_checker(event, attributes)"
        A1["1. Call base all_checker"]
        A2["2. Extract input value from event attributes"]
        A3["3. Store in marking.event_values"]

        A1 --> A2 --> A3
    end

    style E4 fill:#f44336,color:#fff
    style E6 fill:#f44336,color:#fff
```

---

## 9. Replay Algorithm (Conformance)

The conformance replay iterates over each trace in the event log:

```mermaid
flowchart TD
    Start["For each trace"] --> Init["Save initial marking<br/>(including eventValues)"]
    Init --> Loop

    subgraph "For each event in trace"
        Loop["Get event e from log"]
        Loop --> Track["Track response origins<br/>(unguarded + guarded)"]
        Track --> All["all_checker(e, attributes)<br/>• Base checks<br/>• Extract data values"]
        All --> EnQ{"is_enabled(e)?"}
        EnQ -->|No| EnCheck["enabled_checker(e)<br/>• Condition violations<br/>• Data guard violations"]
        EnQ -->|Yes| Exec
        EnCheck --> Exec

        Exec{"Input event?"}
        Exec -->|Yes| ExecData["execute(e, input_value=v)<br/>Value from log attribute"]
        Exec -->|No| ExecNorm["execute(e)"]

        ExecData --> Fulfill
        ExecNorm --> Fulfill
        Fulfill["Remove fulfilled responses<br/>from response_origin"]
    end

    Fulfill --> NextEv{"More events?"}
    NextEv -->|Yes| Loop
    NextEv -->|No| Accept

    Accept{"is_accepting()?"}
    Accept -->|No| AccCheck["accepting_checker()<br/>Report unfulfilled responses"]
    Accept -->|Yes| Fit

    AccCheck --> Compute
    Fit --> Compute
    Compute["Compute fitness =<br/>1 - deviations / constraints"]

    Compute --> Reset["Reset marking to initial"]
    Reset --> NextTrace{"More traces?"}
    NextTrace -->|Yes| Start

    style Start fill:#2196f3,color:#fff
    style Fit fill:#4caf50,color:#fff
    style EnCheck fill:#ff9800,color:#fff
    style AccCheck fill:#f44336,color:#fff
```

---

## 10. Running Example: Expense Report

The paper's expense report models an approval workflow where the decision
path depends on the amount and payment type:

```mermaid
graph LR
    Amount["Amount<br/>(input int)"]
    Type["Type<br/>(input int)"]
    Submit["Submit<br/>(void)"]
    Decision["Decision<br/>(decision int)"]
    Approve["Approve<br/>(input int)"]
    Payout["Payout<br/>(void)"]

    Amount -->|"condition"| Submit
    Type -->|"condition"| Submit
    Submit -->|"condition"| Decision
    Submit -->|"response"| Decision

    Decision -.->|"[D=2] response"| Approve
    Decision -.->|"[¬(D=3)] response"| Payout
    Decision -.->|"[D=3] no-response"| Payout
    Decision -.->|"[D=2] include"| Approve
    Decision -.->|"[¬(D=2)] exclude"| Approve
    Approve -.->|"[Appr=1] include"| Payout
    Approve -.->|"[¬(Appr=1)] exclude"| Payout

    style Amount fill:#2196f3,color:#fff
    style Type fill:#2196f3,color:#fff
    style Submit fill:#607d8b,color:#fff
    style Decision fill:#9c27b0,color:#fff
    style Approve fill:#2196f3,color:#fff
    style Payout fill:#607d8b,color:#fff
```

> Solid arrows = unguarded relations.  Dashed arrows = guarded relations
> with guard expression in brackets.

### Three Example Traces

```mermaid
sequenceDiagram
    participant Env as Environment
    participant G as Graph Marking

    Note over Env,G: Trace 1 — Low Cash Expense (Amount=100, Type=1)
    Env->>G: Amount? 100
    Env->>G: Type? 1
    Env->>G: Submit
    Note right of G: Decision expr: 100 < 200 → 1
    Env->>G: Decision (computed: 1)
    Note right of G: ¬(D=3) → Payout pending<br/>¬(D=2) → Approve excluded
    Env->>G: Payout
    Note right of G: ✅ Accepting

    Note over Env,G: Trace 2 — Medium Cash Approved (Amount=800, Type=1)
    Env->>G: Type? 1
    Env->>G: Amount? 800
    Env->>G: Submit
    Note right of G: Decision expr: ¬(800<200), ¬(Type=2), ¬(≥5000∧Type=1) → 2
    Env->>G: Decision (computed: 2)
    Note right of G: D=2 → Approve included & pending<br/>¬(D=3) → Payout pending
    Env->>G: Approve? 1
    Note right of G: Appr=1 → Payout included
    Env->>G: Payout
    Note right of G: ✅ Accepting

    Note over Env,G: Trace 3 — High Cash Rejected (Amount=6000, Type=1)
    Env->>G: Type? 1
    Env->>G: Amount? 6000
    Env->>G: Submit
    Note right of G: Decision expr: ≥5000∧Type=1 → 3
    Env->>G: Decision (computed: 3)
    Note right of G: D=3 → no-response on Payout<br/>¬(D=2) → Approve excluded<br/>D=3 → Payout NOT added to pending
    Note right of G: ✅ Accepting (nothing pending)
```

---

## 11. Module Layout

```
pm4py/objects/dcr/data/
├── expressions.py    # Expression AST, Guard, builder helpers
├── obj.py            # DataMarking, DataDcrGraph
└── semantics.py      # DataSemantics (enabled, execute)

pm4py/algo/conformance/dcr/
├── rules/
│   └── data_guard.py     # CheckDataGuard rule
└── decorators/
    └── datadecorator.py  # DataConstraintDecorator

tests/
└── dcr_data_test.py      # 77 tests across 13 test classes
```
