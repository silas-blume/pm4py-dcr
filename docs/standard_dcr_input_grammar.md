# Standard DCR Input Grammar (PM4Py-DCR)

This document specifies the *actual accepted input grammar* for standard DCR models in this repository, based on parser and object code.

Scope:
- Default importer: XML DCR Portal format (`pm4py.objects.dcr.importer.variants.xml_dcr_portal`)
- Alternate importer: XML Simple format (`pm4py.objects.dcr.importer.variants.xml_simple`)
- Public API: `pm4py.read_dcr_xml(...)`

This is written so it can be used as a strict target for LLM-based generation.

## 1. Input Channels

Standard DCR can be provided through:

1. XML file path:
   - `pm4py.read_dcr_xml(path, **parameters)`
   - Default variant: `XML_DCR_PORTAL`
2. Importer direct call with variant:
   - `pm4py.objects.dcr.importer.importer.apply(path, variant=...)`
3. In-memory XML string:
   - `pm4py.objects.dcr.importer.importer.deserialize(xml_string, variant=...)`

Supported variants:
- `XML_DCR_PORTAL` (default)
- `XML_SIMPLE`

## 2. XML_DCR_PORTAL Grammar (Default)

Important behavior of this parser:
- Tag names are matched in lowercase (`curr_el.tag.lower()`).
- Parsing is recursive over all descendants.
- Unknown tags are ignored.
- Several optional attributes are read but not used for semantics (`filterLevel`, `description`, `groups` on relation tags).

### 2.1 EBNF (Accepted Structure)

The parser is permissive and does not require a strict tree shape, but this is the canonical structure that is expected and interoperable.

```ebnf
Document        = DcrGraph ;

DcrGraph        = "<dcrgraph" TitleAttr? ">"
                    Specification?
                    Runtime?
                    AnyRecognizedElement*
                  "</dcrgraph>" ;

Specification   = "<specification>"
                    Resources?
                    Constraints?
                  "</specification>" ;

Resources       = "<resources>"
                    EventsBlock?
                    LabelsBlock?
                    LabelMappingsBlock?
                    RolesBlock?
                  "</resources>" ;

EventsBlock     = "<events>" Event* "</events>" ;
LabelsBlock     = "<labels>" Label* "</labels>" ;
LabelMappingsBlock = "<labelMappings>" LabelMapping* "</labelMappings>" ;
RolesBlock      = "<roles>" Role* "</roles>" ;

Constraints     = "<constraints>"
                    ConditionsBlock?
                    ResponsesBlock?
                    IncludesBlock?
                    ExcludesBlock?
                    MilestonesBlock?
                    CoResponsesBlock?
                    NoResponsesBlock?
                  "</constraints>" ;

ConditionsBlock = "<conditions>" Condition* "</conditions>" ;
ResponsesBlock  = "<responses>" Response* "</responses>" ;
IncludesBlock   = "<includes>" Include* "</includes>" ;
ExcludesBlock   = "<excludes>" Exclude* "</excludes>" ;
MilestonesBlock = "<milestones>" Milestone* "</milestones>" ;
CoResponsesBlock = "<coResponses>" CoResponse* "</coResponses>" ;
NoResponsesBlock = "<noResponses>" NoResponse* "</noResponses>" ;

Runtime         = "<runtime>" Marking "</runtime>" ;
Marking         = "<marking>"
                    ExecutedBlock?
                    IncludedBlock?
                    PendingResponsesBlock?
                  "</marking>" ;

ExecutedBlock   = "<executed>" EventRef* "</executed>" ;
IncludedBlock   = "<included>" EventRef* "</included>" ;
PendingResponsesBlock = "<pendingResponses>" EventRef* "</pendingResponses>" ;

Event           = "<event" EventIdAttr EventTypeAttr? ">"
                    (Role | ReadRole | Event)*
                  "</event>"
                | "<event" EventIdAttr EventTypeAttr? "/>" ;

EventRef        = "<event" EventIdAttr "/>" | Event ;
Label           = "<label" LabelIdAttr "/>" | "<label" LabelIdAttr "></label>" ;
LabelMapping    = "<labelMapping" EventIdMapAttr LabelIdMapAttr "/>" ;
Role            = "<role>" Text "</role>" ;
ReadRole        = "<readRole>" Text "</readRole>" ;

Condition       = "<condition" SourceIdAttr TargetIdAttr RelationCommonAttrs* "/>" ;
Response        = "<response" SourceIdAttr TargetIdAttr RelationCommonAttrs* "/>" ;
Include         = "<include" SourceIdAttr TargetIdAttr RelationCommonAttrs* "/>" ;
Exclude         = "<exclude" SourceIdAttr TargetIdAttr RelationCommonAttrs* "/>" ;
Milestone       = "<milestone" SourceIdAttr TargetIdAttr RelationCommonAttrs* "/>" ;
CoResponse      = "<coresponse" SourceIdAttr TargetIdAttr RelationCommonAttrs* "/>" ;
NoResponse      = "<noresponse" SourceIdAttr TargetIdAttr RelationCommonAttrs* "/>" ;

RelationCommonAttrs = TimeAttr | FilterLevelAttr | DescriptionAttr | GroupsAttr | AnyAttr ;
```

### 2.2 Recognized Tags and Semantics

`event`:
- Required for creation: `id` attribute must exist.
- Optional `type`:
  - `subprocess` -> creates subprocess node.
  - `nesting` -> creates nested group node.
- If parent event has `type=subprocess` or `type=nesting`, child event is assigned to that group.
- If parent tag is:
  - `executed` -> event id added to marking.executed.
  - `included` -> event id added to marking.included.
  - `pendingResponses` -> event id added to marking.pending.
- Descendant `<role>` and `<readRole>` under this event create event-role assignments.

`label`:
- Reads attribute `id`; inserted into `labels` set.

`labelMapping`:
- Reads `eventId`, `labelId`.
- First mapping per event id wins (duplicate eventId entries after first are ignored).

`condition`:
- Reads `sourceId`, `targetId`.
- Stores relation in `conditionsFor[targetId].add(sourceId)`.
- Optional `time`:
  - If decimal digits only -> `int`.
  - Else -> parsed by `isodate.parse_duration(...)`.
  - Stored in `conditionsForDelays[targetId][sourceId]`.

`response`:
- Reads `sourceId`, `targetId`.
- Stores relation in `responseTo[sourceId].add(targetId)`.
- Optional `time` parsed as above and stored in `responseToDeadlines[sourceId][targetId]`.

`include` / `exclude`:
- Reads `sourceId`, `targetId`.
- Stored in `includesTo[sourceId].add(targetId)` or `excludesTo[sourceId].add(targetId)`.

`coresponse` / `noresponse`:
- Both map to `noResponseTo[sourceId].add(targetId)`.

`milestone`:
- Reads `sourceId`, `targetId`.
- Stored reversed as `milestonesFor[targetId].add(sourceId)`.

Top-level `role`:
- Tag text becomes a role id in `roles`.
- Ensures empty sets exist for both `roleAssignments[role]` and `readRoleAssignments[role]`.

### 2.3 Attributes

Required per relation tag for semantic effect:
- `sourceId`
- `targetId`

Optional and semantically used:
- `time` on `condition` and `response` for timed DCR fields.

Optional but currently ignored by semantics:
- `filterLevel`
- `description`
- `groups`

Other attributes:
- Ignored.

### 2.4 Canonical Minimal Valid XML_DCR_PORTAL Example

```xml
<dcrgraph title="Example">
  <specification>
    <resources>
      <events>
        <event id="A"/>
        <event id="B"/>
      </events>
      <labels>
        <label id="A"/>
        <label id="B"/>
      </labels>
      <labelMappings>
        <labelMapping eventId="A" labelId="A"/>
        <labelMapping eventId="B" labelId="B"/>
      </labelMappings>
    </resources>
    <constraints>
      <conditions>
        <condition sourceId="A" targetId="B"/>
      </conditions>
    </constraints>
  </specification>
  <runtime>
    <marking>
      <executed/>
      <included>
        <event id="A"/>
        <event id="B"/>
      </included>
      <pendingResponses/>
    </marking>
  </runtime>
</dcrgraph>
```

### 2.5 Normalization and Label Mapping Rules

After parse, `clean_input_as_dict(...)` normalizes identifiers:
- `strip()` on ids/texts.
- Replaces spaces with `white_space_replacement` (default `' '`, so effectively unchanged unless overridden).

Then (default) `labels_as_ids=True` triggers `map_labels_to_events(...)`:
- Event ids are rewritten to their label ids using `labelMapping`.
- For robust generation, include a `labelMapping` entry for every event.

## 3. XML_SIMPLE Grammar (Alternate Variant)

This variant is a separate parser with a different schema.

### 3.1 EBNF

```ebnf
SimpleDocument = "<DCRModel>"
                   Title?
                   Description?
                   GraphType?
                   Roles?
                   EventNode*
                   RuleNode*
                 "</DCRModel>" ;

EventNode       = "<events>"
                    "<id>" Text "</id>"
                    "<label>" Text "</label>"
                    ("<parent>" Text "</parent>")?
                    ("<type>" ("subprocess" | "nesting") "</type>")?
                  "</events>" ;

RuleNode        = "<rules>"
                    "<type>" RuleType "</type>"
                    "<source>" Text "</source>"
                    "<target>" Text "</target>"
                    ("<duration>" DurationText "</duration>")?
                  "</rules>" ;

RuleType        = "condition" | "response" | "include" | "exclude" | "milestone" | "coresponse" ;
```

### 3.2 Semantics

- Events are read from repeated `<events>` nodes (not `<event>`).
- Rules are read from repeated `<rules>` nodes.
- `duration` is interpreted as float seconds and converted to `timedelta(seconds=...)`.
- Parsing of spaces in ids/labels replaces spaces with `replace_whitespace` (default `' '`).
- Co-response rules map to `noResponseTo`.

## 4. LLM Generation Checklist (Standard DCR)

For best compatibility with default importer:

1. Use XML_DCR_PORTAL schema with root `<dcrgraph>`.
2. Emit every event in `resources/events/event@id`.
3. Emit one `labelMapping(eventId,labelId)` per event.
4. Use relation tags exactly: `condition`, `response`, `include`, `exclude`, optionally `milestone`, `coresponse`.
5. Add runtime marking with `included` events.
6. If using timed constraints, put them in relation `time` attributes.
7. Avoid relying on `filterLevel`, `description`, `groups` (read but ignored).

## 5. Known Limitations

- No XML parsing for data-aware fields (`eventTypes`, `decisions`, guarded relations) in this importer.
- Unknown tags are silently ignored, so malformed XML can partially parse without explicit failure.
- Label mapping is effectively mandatory when `labels_as_ids=True` (default), otherwise remapping may fail.

## 6. Source of Truth (Code)

- `pm4py/objects/dcr/importer/variants/xml_dcr_portal.py`
- `pm4py/objects/dcr/importer/variants/xml_simple.py`
- `pm4py/objects/dcr/importer/importer.py`
- `pm4py/read.py`
- `pm4py/objects/dcr/obj.py`
- `pm4py/objects/dcr/utils/utils.py`
