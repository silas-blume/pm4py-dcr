# Data-Aware DCR XML Format (`XML_DCR_DATA`)

This document is the authoritative reference for the `XML_DCR_DATA` format —
the XML serialisation of data-aware DCR graphs in PM4Py-DCR.  It is designed
to be used directly by LLMs for generating valid input files.

---

## 1. Overview

The `XML_DCR_DATA` format extends the DCR Portal XML format with three
categories of additions:

| Addition | Where in XML | Purpose |
|---|---|---|
| `dataType` attribute on `<event>` | `<resources>/<events>` | Declares the type of a data event |
| `decision` attribute on `<event>` | `<resources>/<events>` | Declares the decision function (input or computed) |
| `<guardedConditions>` … `<guardedNoResponses>` sections | `<constraints>` | Guarded relations with boolean guards |
| `<eventValues>` section | `<runtime>/<marking>` | Initial/current event values |

All standard portal-format elements (unguarded conditions, responses,
includes, excludes, milestones, no-responses, roles, subprocesses) continue
to work unchanged.

---

## 2. Complete XML Schema

```xml
<?xml version="1.0" encoding="UTF-8"?>
<dcrgraph title="Graph Title">

  <specification>
    <resources>

      <!-- Events: can carry dataType and decision attributes -->
      <events>
        <event id="EventId"
               dataType="int|bool|void"
               decision="?|expression_string"/>
        <!-- ... more events ... -->
      </events>

      <!-- Labels (activity names) — one per event -->
      <labels>
        <label id="ActivityName"/>
      </labels>

      <!-- Label mappings — links event IDs to activity labels -->
      <labelMappings>
        <labelMapping eventId="EventId" labelId="ActivityName"/>
      </labelMappings>

    </resources>

    <constraints>

      <!-- ── Unguarded relations (standard portal format) ─────────────── -->

      <conditions>
        <condition sourceId="E1" targetId="E2" time="P1D"/>
        <!-- sourceId must be executed before targetId can fire -->
      </conditions>

      <responses>
        <response sourceId="E1" targetId="E2" time="P7D"/>
        <!-- executing E1 makes E2 pending -->
      </responses>

      <excludes>
        <exclude sourceId="E1" targetId="E2"/>
        <!-- executing E1 excludes E2 -->
      </excludes>

      <includes>
        <include sourceId="E1" targetId="E2"/>
        <!-- executing E1 includes E2 -->
      </includes>

      <milestones>
        <milestone sourceId="E1" targetId="E2"/>
        <!-- E1 pending blocks E2 -->
      </milestones>

      <coresponces>
        <coresponse sourceId="E1" targetId="E2"/>
        <!-- executing E1 removes E2 from pending -->
      </coresponces>

      <!-- ── Guarded relations (new in XML_DCR_DATA) ─────────────────── -->
      <!-- The guard attribute is an expression string (see Section 4).   -->
      <!-- If guard is absent, the guard is trivially true.               -->

      <guardedConditions>
        <!-- target → source orientation (same as unguarded conditions)   -->
        <condition sourceId="E1" targetId="E2" guard="[E1] &gt; 0"/>
      </guardedConditions>

      <guardedResponses>
        <!-- source → target orientation                                   -->
        <response sourceId="E1" targetId="E2" guard="[E1] == 2"/>
      </guardedResponses>

      <guardedIncludes>
        <include sourceId="E1" targetId="E2" guard="[E1] == 2"/>
      </guardedIncludes>

      <guardedExcludes>
        <exclude sourceId="E1" targetId="E2" guard="(not ([E1] == 2))"/>
      </guardedExcludes>

      <guardedMilestones>
        <!-- target → source orientation (same as unguarded milestones)   -->
        <milestone sourceId="E1" targetId="E2" guard="[E1] &gt; 100"/>
      </guardedMilestones>

      <guardedNoResponses>
        <noresponse sourceId="E1" targetId="E2" guard="[E1] == 3"/>
      </guardedNoResponses>

    </constraints>
  </specification>

  <runtime>
    <marking>
      <executed>
        <event id="E1"/>   <!-- events that have been executed -->
      </executed>
      <included>
        <event id="E2"/>   <!-- events currently in scope -->
      </included>
      <pendingResponses>
        <event id="E3"/>   <!-- events with outstanding response obligations -->
      </pendingResponses>

      <!-- Initial / current data values for events (new in XML_DCR_DATA) -->
      <eventValues>
        <eventValue id="Amount" value="800"/>
        <eventValue id="Approved" value="true"/>
      </eventValues>

    </marking>
  </runtime>

</dcrgraph>
```

---

## 3. `<event>` Attributes

| Attribute | Required | Values | Description |
|---|---|---|---|
| `id` | yes | string | Unique identifier for the event |
| `type` | no | `subprocess`, `nesting` | Hierarchical group type (standard portal) |
| `dataType` | no | `int`, `bool`, `void` | Data type of the event's value |
| `decision` | no | `?` or expression string | `?` = input event; expression = decision event |

**Decision options:**
- **`?`** — input event: the value is provided by the environment (event log) at execution time.
- **Expression string** — decision event: the value is computed from the expression when the event fires.
- **Omitted** — void event (no data tracked).

---

## 4. Expression String Syntax

Expression strings appear as attribute values in `decision=` and `guard=`.
They are human-readable and XML entities (`&lt;`, `&gt;`, `&amp;`) apply
as usual in XML attributes.

### 4.1 Atom Types

| Syntax | Meaning | Example |
|---|---|---|
| `?` | Input marker (only in `decision=`) | `decision="?"` |
| `void` | Void decision (only in `decision=`) | `decision="void"` |
| `42` | Integer constant | `42`, `-5` |
| `true` / `false` | Boolean constant | `true`, `false` |
| `[EventId]` | Reference to another event's current value | `[Amount]`, `[My Event]` |

**Event IDs** are enclosed in `[…]`; they may contain spaces and special
characters except `]`.

### 4.2 Arithmetic Operators

| Operator | Syntax | Precedence |
|---|---|---|
| Addition | `[A] + [B]` | lower |
| Subtraction | `[A] - [B]` | lower |
| Multiplication | `[A] * [B]` | higher |

Multiplication binds tighter than addition/subtraction.

### 4.3 Comparison Operators

All comparisons produce a boolean result.

| Operator | Syntax |
|---|---|
| Equal | `[A] == 2` |
| Less than | `[A] &lt; 200` (`<` encoded as `&lt;`) |
| Greater than | `[A] &gt; 0` (`>` encoded as `&gt;`) |
| Less than or equal | `[A] &lt;= 200` |
| Greater than or equal | `[A] &gt;= 200` |

### 4.4 Boolean Operators

| Operator | Syntax | Precedence |
|---|---|---|
| Negation | `not [A]` | highest of bool ops |
| Conjunction | `[A] == 1 and [B] == 2` | higher |
| Disjunction | `[A] == 1 or [B] == 2` | lower |

`and` binds tighter than `or`; use parentheses to override.

### 4.5 Conditional

```
if <condition> then <then_expr> else <else_expr>
```

Nesting is right-associative (the `else` branch can itself be another `if`):

```
if [Amount] &lt; 200 then 1
else if ([Amount] &gt;= 200 and [Type] == 2) then 2
else if ([Amount] &gt;= 5000 and [Type] == 1) then 3
else 2
```

### 4.6 Operator Precedence (lowest to highest)

```
if/then/else
    or
        and
            not
                == < > <= >=
                    +  -
                        *
                            atom  ( )  [EventId]  42  true  false  void
```

### 4.7 XML Encoding Rules

| Character | In XML attribute | In expression string |
|---|---|---|
| `<` | `&lt;` | `<` (after XML parsing) |
| `>` | `&gt;` | `>` (after XML parsing) |
| `&` | `&amp;` | `&` (not used in expressions) |
| `"` | `&quot;` | `"` (not used in expressions) |

lxml handles encoding/decoding automatically; you write the expression with
`<` in Python, and it becomes `&lt;` in the file.

---

## 5. Guarded Relation Orientation

This is the **most common source of errors**. The key (outer dict) direction
differs between condition-like and response-like relations:

| Section | Key (outer dict) | Value (inner dict) | Semantics |
|---|---|---|---|
| `guardedConditions` | `targetId` | `sourceId` → guard | Source must execute before target can fire (if guard true) |
| `guardedMilestones` | `targetId` | `sourceId` → guard | Source pending blocks target (if guard true) |
| `guardedResponses` | `sourceId` | `targetId` → guard | Source firing makes target pending (if guard true) |
| `guardedIncludes` | `sourceId` | `targetId` → guard | Source firing includes target (if guard true) |
| `guardedExcludes` | `sourceId` | `targetId` → guard | Source firing excludes target (if guard true) |
| `guardedNoResponses` | `sourceId` | `targetId` → guard | Source firing removes target from pending (if guard true) |

In XML: `sourceId` and `targetId` attributes on child elements follow
the same convention — see examples below.

---

## 6. `<eventValue>` Value Encoding

| Python type | XML `value` attribute |
|---|---|
| `int` | `"42"`, `"-5"` |
| `bool` | `"true"` or `"false"` |

The type is inferred from the string at parse time: `"true"` / `"false"` become `bool`; anything parseable as an integer becomes `int`.

---

## 7. Complete Example: Expense Report

This reproduces the running example from Hildebrandt et al. (2022).

```xml
<?xml version="1.0" encoding="UTF-8"?>
<dcrgraph title="Expense Report">
  <specification>
    <resources>
      <events>
        <event id="Amount"   dataType="int"  decision="?"/>
        <event id="Type"     dataType="int"  decision="?"/>
        <event id="Submit"   dataType="void"/>
        <event id="Decision" dataType="int"
               decision="if [Amount] &lt; 200 then 1
                         else if ([Amount] &gt;= 200 and [Type] == 2) then 2
                         else if ([Amount] &gt;= 5000 and [Type] == 1) then 3
                         else 2"/>
        <event id="Approve"  dataType="int"  decision="?"/>
        <event id="Payout"   dataType="void"/>
      </events>
      <labels>
        <label id="Amount"/><label id="Type"/><label id="Submit"/>
        <label id="Decision"/><label id="Approve"/><label id="Payout"/>
      </labels>
      <labelMappings>
        <labelMapping eventId="Amount"   labelId="Amount"/>
        <labelMapping eventId="Type"     labelId="Type"/>
        <labelMapping eventId="Submit"   labelId="Submit"/>
        <labelMapping eventId="Decision" labelId="Decision"/>
        <labelMapping eventId="Approve"  labelId="Approve"/>
        <labelMapping eventId="Payout"   labelId="Payout"/>
      </labelMappings>
    </resources>

    <constraints>
      <!-- Unguarded: Amount and Type must run before Submit -->
      <conditions>
        <condition sourceId="Amount" targetId="Submit"/>
        <condition sourceId="Type"   targetId="Submit"/>
        <condition sourceId="Submit" targetId="Decision"/>
      </conditions>
      <!-- Unguarded: submitting creates an obligation to decide -->
      <responses>
        <response sourceId="Submit" targetId="Decision"/>
      </responses>
      <excludes/><includes/><milestones/><coresponces/>

      <!-- Guarded responses from Decision -->
      <guardedResponses>
        <!-- Decision=2  → Approve becomes pending -->
        <response sourceId="Decision" targetId="Approve"
                  guard="[Decision] == 2"/>
        <!-- Decision!=3 → Payout becomes pending -->
        <response sourceId="Decision" targetId="Payout"
                  guard="(not ([Decision] == 3))"/>
      </guardedResponses>

      <!-- Guarded includes -->
      <guardedIncludes>
        <include sourceId="Decision" targetId="Approve"
                 guard="[Decision] == 2"/>
        <include sourceId="Approve"  targetId="Payout"
                 guard="[Approve] == 1"/>
      </guardedIncludes>

      <!-- Guarded excludes -->
      <guardedExcludes>
        <exclude sourceId="Decision" targetId="Approve"
                 guard="(not ([Decision] == 2))"/>
        <exclude sourceId="Approve"  targetId="Payout"
                 guard="(not ([Approve] == 1))"/>
      </guardedExcludes>

      <!-- Guarded no-response: rejection cancels payout -->
      <guardedNoResponses>
        <noresponse sourceId="Decision" targetId="Payout"
                    guard="[Decision] == 3"/>
      </guardedNoResponses>

      <guardedConditions/><guardedMilestones/>
    </constraints>
  </specification>

  <runtime>
    <marking>
      <executed/>
      <!-- Approve starts excluded (not in included set) -->
      <included>
        <event id="Amount"/><event id="Type"/><event id="Submit"/>
        <event id="Decision"/><event id="Payout"/>
      </included>
      <pendingResponses/>
    </marking>
  </runtime>
</dcrgraph>
```

---

## 8. Python API

### 8.1 Import from file

```python
from pm4py.objects.dcr.importer.importer import apply, XML_DCR_DATA

graph = apply('expense_report.xml', variant=XML_DCR_DATA)
# Returns DataDcrGraph
```

### 8.2 Import from string

```python
from pm4py.objects.dcr.importer.importer import deserialize, XML_DCR_DATA

graph = deserialize(xml_bytes, variant=XML_DCR_DATA)
```

### 8.3 Export to file

```python
from pm4py.objects.dcr.exporter.exporter import apply, XML_DCR_DATA

apply(graph, 'output.xml', variant=XML_DCR_DATA)
```

### 8.4 Export to bytes (in-memory)

```python
from pm4py.objects.dcr.exporter.variants.xml_dcr_data import export_to_string

xml_bytes = export_to_string(graph)
```

### 8.5 Build and export a graph programmatically

```python
from pm4py.objects.dcr.data.expressions import (
    DataType, Guard, INPUT_MARKER, const, event_ref, eq, lt, if_then_else, not_,
)
from pm4py.objects.dcr.data.obj import DataDcrGraph
from pm4py.objects.dcr.exporter.exporter import apply, XML_DCR_DATA

g = DataDcrGraph()
g.events = {'Amount', 'Decision', 'Payout'}
g.marking.included = {'Amount', 'Decision', 'Payout'}
g.labels = g.events.copy()
g.label_map = {e: e for e in g.events}

g.event_types = {
    'Amount':   DataType.INT,
    'Decision': DataType.INT,
    'Payout':   DataType.VOID,
}
g.decisions = {
    'Amount':   INPUT_MARKER,
    'Decision': if_then_else(lt(event_ref('Amount'), const(200)), const(1), const(2)),
}

g.conditions = {'Decision': {'Amount'}}
g.guarded_responses = {
    'Decision': {'Payout': Guard(not_(eq(event_ref('Decision'), const(3))))}
}

apply(g, 'my_graph.xml', variant=XML_DCR_DATA)
```

---

## 9. Expression String Parser API

The parser lives in `pm4py/objects/dcr/data/expression_parser.py`.

```python
from pm4py.objects.dcr.data.expression_parser import (
    parse_expression,  # str  → Expression | INPUT_MARKER
    parse_guard,       # str  → Guard  (empty string → trivial guard)
    serialize_expression,  # Expression | INPUT_MARKER → str
    serialize_guard,       # Guard → str  (trivial → empty string)
)
```

All serialised expressions round-trip through `parse_expression(serialize_expression(e))`.

---

## 10. LLM Generation Contract

Use these rules to generate valid `XML_DCR_DATA` input:

### 10.1 Mandatory structure

1. Root element: `<dcrgraph title="...">`.
2. `<specification>/<resources>/<events>` — one `<event id="..."/>` per event.
3. `<specification>/<resources>/<labels>` — one `<label id="..."/>` per activity label.
4. `<specification>/<resources>/<labelMappings>` — one `<labelMapping eventId="..." labelId="..."/>` linking event to label.
5. `<specification>/<constraints>` — at minimum `<conditions/>`, `<responses/>`, `<excludes/>`, `<includes/>`, `<milestones/>`, `<coresponces/>`.
6. `<runtime>/<marking>` with `<executed/>`, `<included>`, `<pendingResponses/>`.

### 10.2 Data-aware additions

7. Add `dataType="int|bool|void"` to events that carry data.
8. Add `decision="?"` to input events, `decision="<expr>"` to decision events.
9. Add guarded relation sections inside `<constraints>` as needed (can be empty: `<guardedConditions/>`).
10. Add `<eventValues>` inside `<marking>` if there are initial event values.

### 10.3 Expression string rules

11. Use `[EventId]` for event references (brackets required, spaces OK inside).
12. Use `&lt;` and `&gt;` for `<` and `>` in XML attributes.
13. Comparison operator is `==` (double equals), not `=`.
14. Boolean operators are lowercase keywords: `and`, `or`, `not`.
15. `if/then/else` requires all three parts.
16. Use parentheses for complex subexpressions: `(not ([A] == 2))`.

### 10.4 Orientation rules (critical)

17. `guardedConditions` and `guardedMilestones`: **target → source** (`targetId` is the key of the outer dict).
18. All other guarded sections: **source → target** (`sourceId` is the key of the outer dict).
19. In XML child elements, always write both `sourceId` and `targetId` attributes.

### 10.5 Completeness rules

20. Every event referenced in a `decision=` or `guard=` expression must also appear in `<events>`.
21. Every event that will carry a value (input or decision) must have `dataType` set.
22. Guards referencing event values assume those events have been executed; if the referenced event has not fired, the guard evaluates to `false` (relation inactive).

### 10.6 Common mistakes to avoid

| Mistake | Correct form |
|---|---|
| `[A] = 5` (single equals) | `[A] == 5` |
| `[A] < 5` (bare `<` in attribute) | `[A] &lt; 5` |
| `decision="Amount"` (bare event ID) | `decision="?"` or `decision="[Amount]"` |
| `guardedConditions source → target` | `guardedConditions target → source` |
| Omitting `<labels>` / `<labelMappings>` | Always include them |
| `dataType="integer"` | `dataType="int"` |
| `value="TRUE"` | `value="true"` (lowercase) |

---

## 11. Source Files

| File | Role |
|---|---|
| `pm4py/objects/dcr/data/expression_parser.py` | Tokeniser + recursive descent parser, serialiser |
| `pm4py/objects/dcr/importer/variants/xml_dcr_data.py` | XML importer |
| `pm4py/objects/dcr/exporter/variants/xml_dcr_data.py` | XML exporter |
| `pm4py/objects/dcr/importer/importer.py` | Registry (`XML_DCR_DATA` variant) |
| `pm4py/objects/dcr/exporter/exporter.py` | Registry (`XML_DCR_DATA` variant) |
| `pm4py/objects/dcr/utils/utils.py` | `clean_input_as_dict`, `map_labels_to_events` |
| `tests/dcr_data_xml_test.py` | 91 tests (parser, importer, exporter, round-trip) |
