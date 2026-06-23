"""
Data-aware DCR XML exporter (XML_DCR_DATA variant).

Writes a :class:`~pm4py.objects.dcr.data.obj.DataDcrGraph` to disk in an
extended DCR Portal XML format that includes:

* ``dataType`` and ``decision`` attributes on ``<event>`` elements
* ``<guardedConditions>``, ``<guardedResponses>``, ``<guardedIncludes>``,
  ``<guardedExcludes>``, ``<guardedMilestones>``, ``<guardedNoResponses>``
  sections inside ``<constraints>``, with ``guard`` attributes on child elements
* ``<eventValues>`` section inside ``<marking>``

The file can be re-imported with
:mod:`pm4py.objects.dcr.importer.variants.xml_dcr_data`.

See Also
--------
pm4py.objects.dcr.exporter.variants.xml_dcr_portal : base exporter
pm4py.objects.dcr.data.expression_parser : expression string serialisation
"""

from lxml import etree

from pm4py.objects.dcr.data.obj import DataDcrGraph
from pm4py.objects.dcr.data.expressions import DataType
from pm4py.objects.dcr.data.expression_parser import serialize_expression, serialize_guard
from pm4py.objects.dcr.obj import DcrGraph

# Ordered list of (dcr_template_key, section_tag, child_tag, key_attr, val_attr)
# describing the guarded relation sections to write.
_GUARDED_SECTIONS = [
    # (dict key,           section tag,           child tag,    key attr,    val attr)
    ('guardedConditions',  'guardedConditions',   'condition',  'targetId',  'sourceId'),
    ('guardedResponses',   'guardedResponses',    'response',   'sourceId',  'targetId'),
    ('guardedIncludes',    'guardedIncludes',     'include',    'sourceId',  'targetId'),
    ('guardedExcludes',    'guardedExcludes',     'exclude',    'sourceId',  'targetId'),
    ('guardedMilestones',  'guardedMilestones',   'milestone',  'targetId',  'sourceId'),
    ('guardedNoResponses', 'guardedNoResponses',  'noresponse', 'sourceId',  'targetId'),
]


def export_dcr_xml(graph, output_file_name, dcr_title='DCR from pm4py', **parameters):
    """
    Write a DCR graph to a data-aware XML file.

    If *graph* is a :class:`DataDcrGraph`, all data-aware fields are written.
    If it is a plain :class:`DcrGraph`, only the standard portal fields are
    written (same output as the base exporter).

    Parameters
    ----------
    graph : DcrGraph or DataDcrGraph
        The graph to export.
    output_file_name : str or Path
        Destination file path.
    dcr_title : str
        Value written to the ``title`` attribute of ``<dcrgraph>``.
    """
    root = _build_xml(graph, dcr_title)
    tree = etree.ElementTree(root)
    tree.write(output_file_name, pretty_print=True, xml_declaration=True,
               encoding='UTF-8')


def export_to_string(graph, dcr_title='DCR from pm4py', **parameters) -> bytes:
    """
    Serialise a DCR graph to an XML byte string.

    Parameters
    ----------
    graph : DcrGraph or DataDcrGraph
    dcr_title : str

    Returns
    -------
    bytes
        UTF-8 encoded XML.
    """
    root = _build_xml(graph, dcr_title)
    return etree.tostring(root, pretty_print=True, xml_declaration=True,
                          encoding='UTF-8')


# ---------------------------------------------------------------------------
# Internal builder
# ---------------------------------------------------------------------------

def _build_xml(graph, dcr_title: str):
    root = etree.Element('dcrgraph')
    root.set('title', dcr_title)

    specification = etree.SubElement(root, 'specification')
    resources = etree.SubElement(specification, 'resources')
    events_el = etree.SubElement(resources, 'events')
    labels_el = etree.SubElement(resources, 'labels')
    label_mappings_el = etree.SubElement(resources, 'labelMappings')

    constraints = etree.SubElement(specification, 'constraints')
    conditions_el = etree.SubElement(constraints, 'conditions')
    responses_el = etree.SubElement(constraints, 'responses')
    excludes_el = etree.SubElement(constraints, 'excludes')
    includes_el = etree.SubElement(constraints, 'includes')
    milestones_el = etree.SubElement(constraints, 'milestones')
    noresponses_el = etree.SubElement(constraints, 'coresponces')

    # Guarded sections (only meaningful for DataDcrGraph)
    guarded_els = {}
    if isinstance(graph, DataDcrGraph):
        for dcr_key, section_tag, _, _, _ in _GUARDED_SECTIONS:
            guarded_els[dcr_key] = etree.SubElement(constraints, section_tag)

    runtime = etree.SubElement(root, 'runtime')
    marking_el = etree.SubElement(runtime, 'marking')
    executed_el = etree.SubElement(marking_el, 'executed')
    included_el = etree.SubElement(marking_el, 'included')
    pending_el = etree.SubElement(marking_el, 'pendingResponses')
    if isinstance(graph, DataDcrGraph):
        event_values_el = etree.SubElement(marking_el, 'eventValues')
    else:
        event_values_el = None

    is_data = isinstance(graph, DataDcrGraph)

    # --- Events, labels, labelMappings ---
    for event in sorted(graph.events):  # sorted for deterministic output
        label = graph.label_map.get(event, event)

        ev_el = etree.SubElement(events_el, 'event')
        ev_el.set('id', event)

        if is_data:
            # dataType attribute
            data_type = graph.event_types.get(event)
            if data_type is not None:
                ev_el.set('dataType', data_type.value)  # 'int', 'bool', 'void'

            # decision attribute
            decision = graph.decisions.get(event)
            if decision is not None:
                ev_el.set('decision', serialize_expression(decision))

        lbl_el = etree.SubElement(labels_el, 'label')
        lbl_el.set('id', label)

        lm_el = etree.SubElement(label_mappings_el, 'labelMapping')
        lm_el.set('eventId', event)
        lm_el.set('labelId', label)

    # --- Standard (unguarded) constraints ---
    for target, sources in sorted(graph.conditions.items()):
        for source in sorted(sources):
            el = etree.SubElement(conditions_el, 'condition')
            el.set('sourceId', source)
            el.set('targetId', target)

    for source, targets in sorted(graph.responses.items()):
        for target in sorted(targets):
            el = etree.SubElement(responses_el, 'response')
            el.set('sourceId', source)
            el.set('targetId', target)

    for source, targets in sorted(graph.excludes.items()):
        for target in sorted(targets):
            el = etree.SubElement(excludes_el, 'exclude')
            el.set('sourceId', source)
            el.set('targetId', target)

    for source, targets in sorted(graph.includes.items()):
        for target in sorted(targets):
            el = etree.SubElement(includes_el, 'include')
            el.set('sourceId', source)
            el.set('targetId', target)

    if hasattr(graph, 'milestones'):
        for target, sources in sorted(graph.milestones.items()):
            for source in sorted(sources):
                el = etree.SubElement(milestones_el, 'milestone')
                el.set('sourceId', source)
                el.set('targetId', target)

    if hasattr(graph, 'noresponses'):
        for source, targets in sorted(graph.noresponses.items()):
            for target in sorted(targets):
                el = etree.SubElement(noresponses_el, 'coresponse')
                el.set('sourceId', source)
                el.set('targetId', target)

    # --- Guarded constraints ---
    if is_data:
        for dcr_key, _, child_tag, key_attr, val_attr in _GUARDED_SECTIONS:
            section_el = guarded_els[dcr_key]
            guarded_map = getattr(graph, _dcr_key_to_attr(dcr_key))
            for key_id, nested in sorted(guarded_map.items()):
                for val_id, guard in sorted(nested.items()):
                    child = etree.SubElement(section_el, child_tag)
                    child.set(key_attr, key_id)
                    child.set(val_attr, val_id)
                    guard_str = serialize_guard(guard)
                    if guard_str:
                        child.set('guard', guard_str)

    # --- Marking ---
    for event in sorted(graph.marking.executed):
        ev = etree.SubElement(executed_el, 'event')
        ev.set('id', event)

    for event in sorted(graph.marking.included):
        ev = etree.SubElement(included_el, 'event')
        ev.set('id', event)

    for event in sorted(graph.marking.pending):
        ev = etree.SubElement(pending_el, 'event')
        ev.set('id', event)

    # --- Event values ---
    if is_data and event_values_el is not None:
        for event_id, value in sorted(graph.marking.event_values.items()):
            ev_val = etree.SubElement(event_values_el, 'eventValue')
            ev_val.set('id', event_id)
            if isinstance(value, bool):
                ev_val.set('value', 'true' if value else 'false')
            else:
                ev_val.set('value', str(value))

    return root


def _dcr_key_to_attr(dcr_key: str) -> str:
    """Map a DataDcrGraph template key to the property name on the object."""
    mapping = {
        'guardedConditions':  'guarded_conditions',
        'guardedResponses':   'guarded_responses',
        'guardedIncludes':    'guarded_includes',
        'guardedExcludes':    'guarded_excludes',
        'guardedMilestones':  'guarded_milestones',
        'guardedNoResponses': 'guarded_noresponses',
    }
    return mapping[dcr_key]
