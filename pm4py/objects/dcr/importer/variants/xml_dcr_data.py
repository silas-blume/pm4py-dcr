"""
Data-aware DCR XML importer (XML_DCR_DATA variant).

Extends the DCR Portal XML format with data-specific elements:

* ``dataType`` attribute on ``<event>`` — ``"int"``, ``"bool"``, or ``"void"``
* ``decision`` attribute on ``<event>`` — ``"?"`` (input) or an expression string
* ``<guardedConditions>``, ``<guardedResponses>``, ``<guardedIncludes>``,
  ``<guardedExcludes>``, ``<guardedMilestones>``, ``<guardedNoResponses>``
  constraint sections, each containing the same child elements as their
  unguarded counterparts but with an additional ``guard`` attribute
* ``<eventValues>`` section inside ``<marking>`` — child elements
  ``<eventValue id="..." value="..."/>``

All unguarded elements from the base portal format are also accepted, so
a data-aware graph can be a strict superset of a portal graph.

The XML is parsed into a ``dict`` using the base ``dcr_template`` extended
with data keys, then :func:`cast_to_dcr_object` promotes it to a
:class:`DataDcrGraph`.

See Also
--------
pm4py.objects.dcr.importer.variants.xml_dcr_portal : base importer
pm4py.objects.dcr.data.expression_parser : expression string parsing
"""

import copy

from pm4py.objects.dcr.obj import dcr_template
from pm4py.objects.dcr.utils.utils import cast_to_dcr_object, clean_input_as_dict
from pm4py.objects.dcr.data.expressions import DataType, Guard
from pm4py.objects.dcr.data.expression_parser import parse_expression, parse_guard
from pm4py.util import constants

# Maps the new guarded constraint section names to the dcr_template keys
_GUARDED_SECTION_MAP = {
    'guardedconditions':   ('guardedConditions',   'conditionsFor',  'targetId', 'sourceId'),
    'guardedresponses':    ('guardedResponses',     'responseTo',     'sourceId', 'targetId'),
    'guardedincludes':     ('guardedIncludes',      'includesTo',     'sourceId', 'targetId'),
    'guardedexcludes':     ('guardedExcludes',      'excludesTo',     'sourceId', 'targetId'),
    'guardedmilestones':   ('guardedMilestones',    'milestonesFor',  'targetId', 'sourceId'),
    'guardednoresponses':  ('guardedNoResponses',   'noResponseTo',   'sourceId', 'targetId'),
}

# Child element tag names that appear inside guarded sections
_GUARDED_CHILD_TAGS = frozenset({
    'condition', 'response', 'include', 'exclude', 'milestone',
    'coresponse', 'noresponse',
})


def apply(path, parameters=None):
    """
    Read a data-aware DCR graph from an XML file.

    Parameters
    ----------
    path : str or Path
        Path to the XML file.
    parameters : dict, optional

    Returns
    -------
    DataDcrGraph
    """
    if parameters is None:
        parameters = {}

    from lxml import etree, objectify

    parser = etree.XMLParser(remove_comments=True)
    xml_tree = objectify.parse(path, parser=parser)
    return import_xml_tree_from_root(xml_tree.getroot(), **parameters)


def import_from_string(dcr_string, parameters=None):
    """
    Read a data-aware DCR graph from an XML string.

    Parameters
    ----------
    dcr_string : str or bytes
    parameters : dict, optional

    Returns
    -------
    DataDcrGraph
    """
    if parameters is None:
        parameters = {}

    if isinstance(dcr_string, str):
        dcr_string = dcr_string.encode(constants.DEFAULT_ENCODING)

    from lxml import etree, objectify

    parser = etree.XMLParser(remove_comments=True)
    root = objectify.fromstring(dcr_string, parser=parser)
    return import_xml_tree_from_root(root, **parameters)


def import_xml_tree_from_root(root, white_space_replacement=' ',
                               as_dcr_object=True, labels_as_ids=True):
    """
    Parse an lxml element tree root into a data-aware DCR graph.

    Parameters
    ----------
    root : lxml.objectify element
        Root ``<dcrgraph>`` element.
    white_space_replacement : str
        Character used to replace whitespace in event/label IDs.
    as_dcr_object : bool
        If True, calls :func:`cast_to_dcr_object` to return a typed object.
    labels_as_ids : bool
        If True, maps label names to event IDs (standard portal behaviour).

    Returns
    -------
    DataDcrGraph or dict
    """
    dcr = copy.deepcopy(dcr_template)
    context = _ParseContext()
    _parse_element(root, parent=None, dcr=dcr, ctx=context)
    dcr = clean_input_as_dict(dcr, white_space_replacement=white_space_replacement)

    if labels_as_ids:
        from pm4py.objects.dcr.utils.utils import map_labels_to_events
        dcr = map_labels_to_events(dcr)

    if as_dcr_object:
        return cast_to_dcr_object(dcr)
    return dcr


# ---------------------------------------------------------------------------
# Parse context (tracks which guarded section we are inside)
# ---------------------------------------------------------------------------

class _ParseContext:
    """Lightweight mutable state threaded through the recursive parser."""

    def __init__(self):
        # When inside a guarded section, holds the dcr_template key name
        # (e.g. 'guardedResponses') and the orientation tuple
        self.guarded_key: str | None = None
        self.key_field: str | None = None   # 'sourceId' or 'targetId' for the dict key
        self.val_field: str | None = None   # the other field (for the nested dict)


# ---------------------------------------------------------------------------
# Recursive parser
# ---------------------------------------------------------------------------

def _parse_element(curr_el, parent, dcr: dict, ctx: _ParseContext):
    tag = curr_el.tag.lower()

    # ---- Guarded section container tags ----
    if tag in _GUARDED_SECTION_MAP:
        dcr_key, _, key_field, val_field = _GUARDED_SECTION_MAP[tag]
        child_ctx = _ParseContext()
        child_ctx.guarded_key = dcr_key
        child_ctx.key_field = key_field
        child_ctx.val_field = val_field
        for child in curr_el:
            _parse_element(child, curr_el, dcr, child_ctx)
        return

    # ---- Guarded relation child element ----
    if ctx.guarded_key is not None and tag in _GUARDED_CHILD_TAGS:
        key_id = curr_el.get(ctx.key_field)
        val_id = curr_el.get(ctx.val_field)
        guard_str = curr_el.get('guard', '')
        if key_id and val_id:
            guarded_map = dcr[ctx.guarded_key]
            if key_id not in guarded_map:
                guarded_map[key_id] = {}
            guarded_map[key_id][val_id] = parse_guard(guard_str)
        return

    match tag:
        case 'event':
            _parse_event(curr_el, parent, dcr)

        case 'label':
            id_ = curr_el.get('id')
            if id_:
                dcr['labels'].add(id_)

        case 'labelmapping':
            event_id = curr_el.get('eventId')
            label_id = curr_el.get('labelId')
            if event_id and label_id:
                dcr['labelMapping'][event_id] = label_id

        case 'condition':
            _parse_condition(curr_el, dcr)

        case 'response':
            _parse_response(curr_el, dcr)

        case 'include' | 'exclude':
            _parse_include_exclude(curr_el, tag, dcr)

        case 'coresponse' | 'noresponse':
            _parse_noresponse(curr_el, dcr)

        case 'milestone':
            _parse_milestone(curr_el, dcr)

        case 'role':
            if curr_el.text:
                dcr['roles'].add(curr_el.text)
                dcr['roleAssignments'].setdefault(curr_el.text, set())
                dcr['readRoleAssignments'].setdefault(curr_el.text, set())

        case 'eventvalue':
            _parse_event_value(curr_el, dcr)

        case _:
            pass  # traverse into unknown container elements

    for child in curr_el:
        _parse_element(child, curr_el, dcr, ctx)


# ---------------------------------------------------------------------------
# Element-specific parsers
# ---------------------------------------------------------------------------

def _parse_event(el, parent, dcr: dict):
    event_id = el.get('id')
    if not event_id:
        return

    dcr['events'].add(event_id)

    # Hierarchical type
    event_type = el.get('type')
    if event_type == 'subprocess':
        dcr['subprocesses'][event_id] = set()
    elif event_type == 'nesting':
        dcr['nestedgroups'][event_id] = set()

    # Parent nesting
    if parent is not None:
        parent_type = parent.get('type')
        parent_id = parent.get('id')
        if parent_id:
            if parent_type == 'subprocess':
                dcr['subprocesses'].setdefault(parent_id, set()).add(event_id)
            elif parent_type == 'nesting':
                dcr['nestedgroups'].setdefault(parent_id, set()).add(event_id)

    # Marking context
    if parent is not None:
        parent_tag = parent.tag.lower() if hasattr(parent, 'tag') else ''
        if parent_tag in ('included', 'executed'):
            dcr['marking'][parent_tag].add(event_id)
        elif parent_tag == 'pendingresponses':
            dcr['marking']['pending'].add(event_id)

    # Roles
    for role_el in el.findall('.//role'):
        if role_el.text:
            dcr['roleAssignments'].setdefault(role_el.text, set()).add(event_id)
    for role_el in el.findall('.//readRole'):
        if role_el.text:
            dcr['readRoleAssignments'].setdefault(role_el.text, set()).add(event_id)

    # --- Data-aware attributes ---
    data_type_str = el.get('dataType')
    if data_type_str:
        try:
            dcr['eventTypes'][event_id] = DataType(data_type_str.lower())
        except ValueError:
            pass  # unknown type string — skip

    decision_str = el.get('decision')
    if decision_str is not None:
        dcr['decisions'][event_id] = parse_expression(decision_str)


def _parse_event_value(el, dcr: dict):
    """Parse ``<eventValue id="..." value="..."/>`` inside ``<eventValues>``."""
    event_id = el.get('id')
    raw = el.get('value')
    if event_id is None or raw is None:
        return
    # Infer type from value string
    if raw.lower() == 'true':
        value = True
    elif raw.lower() == 'false':
        value = False
    else:
        try:
            value = int(raw)
        except ValueError:
            value = raw  # keep as string if not parseable
    dcr['marking']['eventValues'][event_id] = value


def _parse_condition(el, dcr: dict):
    import isodate
    source = el.get('sourceId')
    target = el.get('targetId')
    if not source or not target:
        return
    dcr['conditionsFor'].setdefault(target, set()).add(source)
    delay = el.get('time')
    if delay:
        dcr['conditionsForDelays'].setdefault(target, {})
        dcr['conditionsForDelays'][target][source] = (
            int(delay) if delay.isdecimal() else isodate.parse_duration(delay)
        )


def _parse_response(el, dcr: dict):
    import isodate
    source = el.get('sourceId')
    target = el.get('targetId')
    if not source or not target:
        return
    dcr['responseTo'].setdefault(source, set()).add(target)
    deadline = el.get('time')
    if deadline:
        dcr['responseToDeadlines'].setdefault(source, {})
        dcr['responseToDeadlines'][source][target] = (
            int(deadline) if deadline.isdecimal() else isodate.parse_duration(deadline)
        )


def _parse_include_exclude(el, tag: str, dcr: dict):
    source = el.get('sourceId')
    target = el.get('targetId')
    if source and target:
        dcr[f'{tag}sTo'].setdefault(source, set()).add(target)


def _parse_noresponse(el, dcr: dict):
    source = el.get('sourceId')
    target = el.get('targetId')
    if source and target:
        dcr['noResponseTo'].setdefault(source, set()).add(target)


def _parse_milestone(el, dcr: dict):
    source = el.get('sourceId')
    target = el.get('targetId')
    if source and target:
        dcr['milestonesFor'].setdefault(target, set()).add(source)
