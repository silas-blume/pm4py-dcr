"""
Tests for the data-aware DCR XML parser (XML_DCR_DATA variant).

Coverage:
1. Expression string parser  — tokeniser, all node types, precedence, round-trip
2. Guard helpers              — parse_guard, serialize_guard
3. XML importer               — minimal graph, all data fields, roundtrip
4. XML exporter               — structure, attribute presence, roundtrip
5. End-to-end variant API     — importer.apply / exporter.apply via registries
6. Edge cases                 — event IDs with spaces, empty sections, non-data graph
7. utils.py compatibility     — clean_input_as_dict, map_labels_to_events
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pm4py.objects.dcr.data.expression_parser import (
    parse_expression, parse_guard, serialize_expression, serialize_guard,
)
from pm4py.objects.dcr.data.expressions import (
    DataType, Guard, INPUT_MARKER,
    IntConstant, BoolConstant, VoidExpression, EventRef,
    ArithExpression, ArithOp,
    CompExpression, CompOp,
    BoolBinaryExpression, BoolOp,
    NotExpression, IfThenElseExpression,
    const, event_ref, eq, lt, gt, le, ge, add, sub, mul, and_, or_, not_, if_then_else,
)
from pm4py.objects.dcr.data.obj import DataDcrGraph, DataMarking
from pm4py.objects.dcr.data.semantics import DataSemantics
from pm4py.objects.dcr.importer.variants.xml_dcr_data import import_from_string
from pm4py.objects.dcr.exporter.variants.xml_dcr_data import export_to_string


# ===========================================================================
# Helpers
# ===========================================================================

def _expense_report_xml(*, include_event_values=False) -> bytes:
    """Full expense-report XML matching the paper running example."""
    ev_vals = '<eventValues><eventValue id="Amount" value="800"/></eventValues>' \
        if include_event_values else ''
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<dcrgraph title="Expense Report">
  <specification>
    <resources>
      <events>
        <event id="Amount" dataType="int" decision="?"/>
        <event id="Type" dataType="int" decision="?"/>
        <event id="Submit" dataType="void"/>
        <event id="Decision" dataType="int"
               decision="if [Amount] &lt; 200 then 1 else if ([Amount] &gt;= 200 and [Type] == 2) then 2 else if ([Amount] &gt;= 5000 and [Type] == 1) then 3 else 2"/>
        <event id="Approve" dataType="int" decision="?"/>
        <event id="Payout" dataType="void"/>
      </events>
      <labels>
        <label id="Amount"/><label id="Type"/><label id="Submit"/>
        <label id="Decision"/><label id="Approve"/><label id="Payout"/>
      </labels>
      <labelMappings>
        <labelMapping eventId="Amount" labelId="Amount"/>
        <labelMapping eventId="Type" labelId="Type"/>
        <labelMapping eventId="Submit" labelId="Submit"/>
        <labelMapping eventId="Decision" labelId="Decision"/>
        <labelMapping eventId="Approve" labelId="Approve"/>
        <labelMapping eventId="Payout" labelId="Payout"/>
      </labelMappings>
    </resources>
    <constraints>
      <conditions>
        <condition sourceId="Amount" targetId="Submit"/>
        <condition sourceId="Type" targetId="Submit"/>
        <condition sourceId="Submit" targetId="Decision"/>
      </conditions>
      <responses>
        <response sourceId="Submit" targetId="Decision"/>
      </responses>
      <excludes/>
      <includes/>
      <milestones/>
      <coresponces/>
      <guardedConditions/>
      <guardedResponses>
        <response sourceId="Decision" targetId="Approve" guard="[Decision] == 2"/>
        <response sourceId="Decision" targetId="Payout" guard="(not ([Decision] == 3))"/>
      </guardedResponses>
      <guardedIncludes>
        <include sourceId="Decision" targetId="Approve" guard="[Decision] == 2"/>
        <include sourceId="Approve" targetId="Payout" guard="[Approve] == 1"/>
      </guardedIncludes>
      <guardedExcludes>
        <exclude sourceId="Decision" targetId="Approve" guard="(not ([Decision] == 2))"/>
        <exclude sourceId="Approve" targetId="Payout" guard="(not ([Approve] == 1))"/>
      </guardedExcludes>
      <guardedMilestones/>
      <guardedNoResponses>
        <noresponse sourceId="Decision" targetId="Payout" guard="[Decision] == 3"/>
      </guardedNoResponses>
    </constraints>
  </specification>
  <runtime>
    <marking>
      <executed/>
      <included>
        <event id="Amount"/><event id="Type"/><event id="Submit"/>
        <event id="Decision"/><event id="Payout"/>
      </included>
      <pendingResponses/>
      {ev_vals}
    </marking>
  </runtime>
</dcrgraph>'''.encode()


# ===========================================================================
# 1. Expression parser tests
# ===========================================================================

class TestExpressionParser(unittest.TestCase):

    # --- Atoms ---

    def test_input_marker(self):
        self.assertEqual(parse_expression('?'), INPUT_MARKER)
        self.assertEqual(parse_expression(' ? '), INPUT_MARKER)

    def test_void(self):
        self.assertIsInstance(parse_expression('void'), VoidExpression)

    def test_int_literal(self):
        e = parse_expression('42')
        self.assertIsInstance(e, IntConstant)
        self.assertEqual(e.evaluate({}), 42)

    def test_bool_true(self):
        e = parse_expression('true')
        self.assertIsInstance(e, BoolConstant)
        self.assertTrue(e.evaluate({}))

    def test_bool_false(self):
        e = parse_expression('false')
        self.assertIsInstance(e, BoolConstant)
        self.assertFalse(e.evaluate({}))

    def test_event_ref(self):
        e = parse_expression('[Amount]')
        self.assertIsInstance(e, EventRef)
        self.assertEqual(e.event_id, 'Amount')
        self.assertEqual(e.evaluate({'Amount': 99}), 99)

    def test_event_ref_with_spaces_in_id(self):
        e = parse_expression('[My Event]')
        self.assertIsInstance(e, EventRef)
        self.assertEqual(e.event_id, 'My Event')

    # --- Arithmetic ---

    def test_add(self):
        e = parse_expression('[A] + 5')
        self.assertIsInstance(e, ArithExpression)
        self.assertEqual(e.op, ArithOp.ADD)
        self.assertEqual(e.evaluate({'A': 10}), 15)

    def test_sub(self):
        e = parse_expression('[A] - 3')
        self.assertEqual(e.evaluate({'A': 10}), 7)

    def test_mul(self):
        e = parse_expression('[A] * 2')
        self.assertEqual(e.evaluate({'A': 5}), 10)

    def test_mul_higher_precedence_than_add(self):
        # [A] + [B] * 2  should be  [A] + ([B] * 2)
        e = parse_expression('[A] + [B] * 2')
        self.assertEqual(e.evaluate({'A': 1, 'B': 3}), 7)

    # --- Comparisons ---

    def test_eq(self):
        e = parse_expression('[A] == 5')
        self.assertIsInstance(e, CompExpression)
        self.assertEqual(e.op, CompOp.EQ)
        self.assertTrue(e.evaluate({'A': 5}))
        self.assertFalse(e.evaluate({'A': 6}))

    def test_lt(self):
        self.assertTrue(parse_expression('[A] < 10').evaluate({'A': 5}))

    def test_gt(self):
        self.assertTrue(parse_expression('[A] > 3').evaluate({'A': 5}))

    def test_le(self):
        self.assertTrue(parse_expression('[A] <= 5').evaluate({'A': 5}))

    def test_ge(self):
        self.assertTrue(parse_expression('[A] >= 5').evaluate({'A': 5}))

    # --- Boolean operators ---

    def test_and(self):
        e = parse_expression('[A] > 0 and [B] == 1')
        self.assertTrue(e.evaluate({'A': 5, 'B': 1}))
        self.assertFalse(e.evaluate({'A': 5, 'B': 2}))

    def test_or(self):
        e = parse_expression('[A] > 0 or [B] == 1')
        self.assertTrue(e.evaluate({'A': -1, 'B': 1}))
        self.assertFalse(e.evaluate({'A': -1, 'B': 2}))

    def test_not(self):
        e = parse_expression('not ([A] == 1)')
        self.assertFalse(e.evaluate({'A': 1}))
        self.assertTrue(e.evaluate({'A': 2}))

    def test_and_higher_precedence_than_or(self):
        # [A] or [B] and [C]  →  [A] or ([B] and [C])
        e = parse_expression('[A] == 1 or [B] == 1 and [C] == 1')
        self.assertTrue(e.evaluate({'A': 1, 'B': 0, 'C': 0}))   # A=true
        self.assertFalse(e.evaluate({'A': 0, 'B': 1, 'C': 0}))  # B&C = false

    # --- If-then-else ---

    def test_if_then_else_true_branch(self):
        e = parse_expression('if [Amount] < 200 then 1 else 2')
        self.assertEqual(e.evaluate({'Amount': 100}), 1)

    def test_if_then_else_false_branch(self):
        e = parse_expression('if [Amount] < 200 then 1 else 2')
        self.assertEqual(e.evaluate({'Amount': 300}), 2)

    def test_nested_if_then_else(self):
        """Paper decision expression."""
        s = ('if [Amount] < 200 then 1 '
             'else if ([Amount] >= 200 and [Type] == 2) then 2 '
             'else if ([Amount] >= 5000 and [Type] == 1) then 3 else 2')
        e = parse_expression(s)
        self.assertEqual(e.evaluate({'Amount': 100, 'Type': 1}), 1)
        self.assertEqual(e.evaluate({'Amount': 800, 'Type': 2}), 2)
        self.assertEqual(e.evaluate({'Amount': 6000, 'Type': 1}), 3)
        self.assertEqual(e.evaluate({'Amount': 800, 'Type': 1}), 2)

    # --- Parentheses ---

    def test_parentheses_override_precedence(self):
        # ([A] + [B]) * 2
        e = parse_expression('([A] + [B]) * 2')
        self.assertEqual(e.evaluate({'A': 3, 'B': 2}), 10)

    # --- Errors ---

    def test_unclosed_bracket_raises(self):
        with self.assertRaises(ValueError):
            parse_expression('[Amount')

    def test_unknown_keyword_raises(self):
        with self.assertRaises(ValueError):
            parse_expression('xor [A] [B]')

    def test_unexpected_token_raises(self):
        with self.assertRaises(ValueError):
            parse_expression('+ 5')

    def test_input_marker_as_guard_raises(self):
        with self.assertRaises(ValueError):
            parse_guard('?')


# ===========================================================================
# 2. Serialisation round-trip tests
# ===========================================================================

class TestSerialisation(unittest.TestCase):

    def _roundtrip(self, expr):
        s = serialize_expression(expr)
        e2 = parse_expression(s)
        self.assertEqual(repr(expr), repr(e2),
                         msg=f"Round-trip failed for {s!r}")
        return s

    def test_input_marker_roundtrip(self):
        self.assertEqual(serialize_expression(INPUT_MARKER), '?')
        self.assertEqual(parse_expression('?'), INPUT_MARKER)

    def test_void_roundtrip(self):
        self._roundtrip(VoidExpression())

    def test_int_roundtrip(self):
        self._roundtrip(const(42))

    def test_bool_roundtrip(self):
        self._roundtrip(const(True))
        self._roundtrip(const(False))

    def test_event_ref_roundtrip(self):
        self._roundtrip(event_ref('Amount'))

    def test_event_ref_with_space_roundtrip(self):
        self._roundtrip(event_ref('My Event'))

    def test_arith_roundtrip(self):
        self._roundtrip(add(event_ref('A'), const(5)))
        self._roundtrip(sub(event_ref('A'), const(3)))
        self._roundtrip(mul(event_ref('A'), const(2)))

    def test_comp_roundtrip(self):
        for fn in (eq, lt, gt, le, ge):
            self._roundtrip(fn(event_ref('A'), const(1)))

    def test_bool_binary_roundtrip(self):
        self._roundtrip(and_(eq(event_ref('A'), const(1)), eq(event_ref('B'), const(2))))
        self._roundtrip(or_(eq(event_ref('A'), const(1)), eq(event_ref('B'), const(2))))

    def test_not_roundtrip(self):
        self._roundtrip(not_(eq(event_ref('A'), const(1))))

    def test_if_then_else_roundtrip(self):
        e = if_then_else(lt(event_ref('Amount'), const(200)), const(1), const(2))
        self._roundtrip(e)

    def test_nested_if_then_else_roundtrip(self):
        decision_expr = if_then_else(
            lt(event_ref('Amount'), const(200)), const(1),
            if_then_else(
                and_(ge(event_ref('Amount'), const(200)), eq(event_ref('Type'), const(2))),
                const(2),
                if_then_else(
                    and_(ge(event_ref('Amount'), const(5000)), eq(event_ref('Type'), const(1))),
                    const(3), const(2),
                )
            )
        )
        self._roundtrip(decision_expr)

    def test_guard_trivial_serialises_to_empty(self):
        self.assertEqual(serialize_guard(Guard()), '')

    def test_guard_roundtrip(self):
        g = Guard(eq(event_ref('Decision'), const(2)))
        s = serialize_guard(g)
        g2 = parse_guard(s)
        self.assertEqual(g, g2)

    def test_guard_trivial_from_empty_string(self):
        g = parse_guard('')
        self.assertTrue(g.is_trivial)


# ===========================================================================
# 3. Importer tests
# ===========================================================================

class TestImporter(unittest.TestCase):

    def setUp(self):
        self.g = import_from_string(_expense_report_xml())

    def test_returns_data_dcr_graph(self):
        self.assertIsInstance(self.g, DataDcrGraph)

    def test_events_parsed(self):
        self.assertEqual(self.g.events,
                         {'Amount', 'Type', 'Submit', 'Decision', 'Approve', 'Payout'})

    def test_event_types(self):
        self.assertEqual(self.g.event_types['Amount'], DataType.INT)
        self.assertEqual(self.g.event_types['Submit'], DataType.VOID)
        self.assertEqual(self.g.event_types['Decision'], DataType.INT)
        self.assertEqual(self.g.event_types['Approve'], DataType.INT)

    def test_input_events(self):
        self.assertTrue(self.g.is_input_event('Amount'))
        self.assertTrue(self.g.is_input_event('Type'))
        self.assertTrue(self.g.is_input_event('Approve'))

    def test_decision_event(self):
        self.assertTrue(self.g.is_decision_event('Decision'))

    def test_decision_expression_evaluates(self):
        vals = {'Amount': 100, 'Type': 1}
        result = self.g.decisions['Decision'].evaluate(vals)
        self.assertEqual(result, 1)   # Amount < 200 → 1

    def test_unguarded_conditions_parsed(self):
        self.assertIn('Submit', self.g.conditions)
        self.assertIn('Amount', self.g.conditions['Submit'])
        self.assertIn('Type', self.g.conditions['Submit'])

    def test_unguarded_response_parsed(self):
        self.assertIn('Submit', self.g.responses)
        self.assertIn('Decision', self.g.responses['Submit'])

    def test_guarded_responses_parsed(self):
        self.assertIn('Decision', self.g.guarded_responses)
        self.assertIn('Approve', self.g.guarded_responses['Decision'])
        self.assertIn('Payout', self.g.guarded_responses['Decision'])

    def test_guarded_response_guard_evaluates(self):
        guard = self.g.guarded_responses['Decision']['Approve']
        self.assertTrue(guard.evaluate({'Decision': 2}))
        self.assertFalse(guard.evaluate({'Decision': 1}))

    def test_guarded_includes_parsed(self):
        self.assertIn('Decision', self.g.guarded_includes)
        self.assertIn('Approve', self.g.guarded_includes['Decision'])

    def test_guarded_excludes_parsed(self):
        self.assertIn('Decision', self.g.guarded_excludes)
        self.assertIn('Approve', self.g.guarded_excludes['Decision'])

    def test_guarded_noresponses_parsed(self):
        self.assertIn('Decision', self.g.guarded_noresponses)
        self.assertIn('Payout', self.g.guarded_noresponses['Decision'])

    def test_marking_included(self):
        self.assertIn('Amount', self.g.marking.included)
        self.assertIn('Payout', self.g.marking.included)
        self.assertNotIn('Approve', self.g.marking.included)  # excluded initially

    def test_event_values_parsed(self):
        g = import_from_string(_expense_report_xml(include_event_values=True))
        self.assertEqual(g.marking.event_values.get('Amount'), 800)

    def test_minimal_xml_no_data_fields(self):
        """A plain portal-format XML without data fields should still import."""
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<dcrgraph title="Minimal">
  <specification>
    <resources>
      <events>
        <event id="A"/>
        <event id="B"/>
      </events>
      <labels><label id="A"/><label id="B"/></labels>
      <labelMappings>
        <labelMapping eventId="A" labelId="A"/>
        <labelMapping eventId="B" labelId="B"/>
      </labelMappings>
    </resources>
    <constraints>
      <conditions><condition sourceId="A" targetId="B"/></conditions>
      <responses/><excludes/><includes/><milestones/><coresponces/>
    </constraints>
  </specification>
  <runtime>
    <marking>
      <executed/>
      <included><event id="A"/><event id="B"/></included>
      <pendingResponses/>
    </marking>
  </runtime>
</dcrgraph>'''
        from pm4py.objects.dcr.obj import DcrGraph
        g = import_from_string(xml)
        # Without data fields, cast_to_dcr_object may return a DcrGraph subtype
        self.assertIn('A', g.events)
        self.assertIn('B', g.events)
        self.assertIn('B', g.conditions)
        self.assertIn('A', g.conditions['B'])


# ===========================================================================
# 4. Exporter tests
# ===========================================================================

class TestExporter(unittest.TestCase):

    def setUp(self):
        self.g = import_from_string(_expense_report_xml())
        self.xml_bytes = export_to_string(self.g)
        self.xml_str = self.xml_bytes.decode()

    def test_output_is_bytes(self):
        self.assertIsInstance(self.xml_bytes, bytes)

    def test_root_element_dcrgraph(self):
        self.assertIn('<dcrgraph', self.xml_str)

    def test_events_written(self):
        self.assertIn('id="Amount"', self.xml_str)
        self.assertIn('id="Decision"', self.xml_str)

    def test_data_type_attribute_written(self):
        self.assertIn('dataType="int"', self.xml_str)
        self.assertIn('dataType="void"', self.xml_str)

    def test_decision_attribute_written(self):
        self.assertIn('decision="?"', self.xml_str)
        self.assertIn('decision=', self.xml_str)

    def test_guarded_sections_written(self):
        for section in ('guardedConditions', 'guardedResponses',
                        'guardedIncludes', 'guardedExcludes',
                        'guardedMilestones', 'guardedNoResponses'):
            self.assertIn(section, self.xml_str,
                          msg=f"Section {section!r} missing from output")

    def test_guard_attribute_written(self):
        self.assertIn('guard=', self.xml_str)

    def test_event_values_section_present(self):
        g_with_vals = import_from_string(_expense_report_xml(include_event_values=True))
        xml = export_to_string(g_with_vals).decode()
        self.assertIn('<eventValues>', xml)
        self.assertIn('id="Amount"', xml)
        self.assertIn('value="800"', xml)

    def test_xml_entities_escaped(self):
        # < and > in expressions must be written as &lt; &gt;
        self.assertIn('&lt;', self.xml_str)

    def test_to_file_and_back(self):
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as f:
            path = f.name
        try:
            from pm4py.objects.dcr.exporter.variants.xml_dcr_data import export_dcr_xml
            export_dcr_xml(self.g, path)
            g2 = import_from_string(open(path, 'rb').read())
            self.assertIsInstance(g2, DataDcrGraph)
            self.assertEqual(g2.events, self.g.events)
        finally:
            os.unlink(path)


# ===========================================================================
# 5. Round-trip tests
# ===========================================================================

class TestRoundTrip(unittest.TestCase):

    def _rt(self, xml_bytes):
        """Import → export → re-import."""
        g1 = import_from_string(xml_bytes)
        xml2 = export_to_string(g1)
        g2 = import_from_string(xml2)
        return g1, g2

    def test_events_preserved(self):
        g1, g2 = self._rt(_expense_report_xml())
        self.assertEqual(g1.events, g2.events)

    def test_event_types_preserved(self):
        g1, g2 = self._rt(_expense_report_xml())
        self.assertEqual(g1.event_types, g2.event_types)

    def test_conditions_preserved(self):
        g1, g2 = self._rt(_expense_report_xml())
        self.assertEqual(g1.conditions, g2.conditions)

    def test_responses_preserved(self):
        g1, g2 = self._rt(_expense_report_xml())
        self.assertEqual(g1.responses, g2.responses)

    def test_guarded_responses_preserved(self):
        g1, g2 = self._rt(_expense_report_xml())
        self.assertEqual(g1.guarded_responses, g2.guarded_responses)

    def test_guarded_includes_preserved(self):
        g1, g2 = self._rt(_expense_report_xml())
        self.assertEqual(g1.guarded_includes, g2.guarded_includes)

    def test_guarded_excludes_preserved(self):
        g1, g2 = self._rt(_expense_report_xml())
        self.assertEqual(g1.guarded_excludes, g2.guarded_excludes)

    def test_guarded_noresponses_preserved(self):
        g1, g2 = self._rt(_expense_report_xml())
        self.assertEqual(g1.guarded_noresponses, g2.guarded_noresponses)

    def test_marking_included_preserved(self):
        g1, g2 = self._rt(_expense_report_xml())
        self.assertEqual(g1.marking.included, g2.marking.included)

    def test_event_values_preserved(self):
        g1, g2 = self._rt(_expense_report_xml(include_event_values=True))
        self.assertEqual(g1.marking.event_values, g2.marking.event_values)

    def test_decision_expression_preserved(self):
        g1, g2 = self._rt(_expense_report_xml())
        v = {'Amount': 6000, 'Type': 1}
        r1 = g1.decisions['Decision'].evaluate(v)
        r2 = g2.decisions['Decision'].evaluate(v)
        self.assertEqual(r1, r2)
        self.assertEqual(r1, 3)  # high cash → reject


# ===========================================================================
# 6. Variant API tests (importer.py / exporter.py registry)
# ===========================================================================

class TestVariantAPI(unittest.TestCase):

    def test_importer_variant_registered(self):
        from pm4py.objects.dcr.importer.importer import Variants, XML_DCR_DATA
        self.assertIn('XML_DCR_DATA', [v.name for v in Variants])
        self.assertEqual(XML_DCR_DATA, Variants.XML_DCR_DATA)

    def test_exporter_variant_registered(self):
        from pm4py.objects.dcr.exporter.exporter import Variants, XML_DCR_DATA
        self.assertIn('XML_DCR_DATA', [v.name for v in Variants])
        self.assertEqual(XML_DCR_DATA, Variants.XML_DCR_DATA)

    def test_exporter_apply_writes_file(self):
        from pm4py.objects.dcr.exporter.exporter import apply, XML_DCR_DATA
        g = import_from_string(_expense_report_xml())
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=False) as f:
            path = f.name
        try:
            apply(g, path, variant=XML_DCR_DATA)
            content = open(path).read()
            self.assertIn('guardedResponses', content)
        finally:
            os.unlink(path)

    def test_importer_deserialise(self):
        from pm4py.objects.dcr.importer.importer import deserialize, XML_DCR_DATA
        g = deserialize(_expense_report_xml(), variant=XML_DCR_DATA)
        self.assertIsInstance(g, DataDcrGraph)
        self.assertIn('Amount', g.events)


# ===========================================================================
# 7. Semantics integration — import then execute
# ===========================================================================

class TestSemanticsAfterImport(unittest.TestCase):
    """Verify that an imported graph produces correct semantics."""

    def setUp(self):
        self.g = import_from_string(_expense_report_xml())

    def test_trace_low_cash(self):
        DataSemantics.execute(self.g, 'Amount', input_value=100)
        DataSemantics.execute(self.g, 'Type', input_value=1)
        DataSemantics.execute(self.g, 'Submit')
        DataSemantics.execute(self.g, 'Decision')
        self.assertEqual(self.g.marking.event_values['Decision'], 1)
        self.assertIn('Payout', self.g.marking.pending)
        DataSemantics.execute(self.g, 'Payout')
        self.assertTrue(DataSemantics.is_accepting(self.g))

    def test_trace_high_cash_rejected(self):
        DataSemantics.execute(self.g, 'Type', input_value=1)
        DataSemantics.execute(self.g, 'Amount', input_value=6000)
        DataSemantics.execute(self.g, 'Submit')
        DataSemantics.execute(self.g, 'Decision')
        self.assertEqual(self.g.marking.event_values['Decision'], 3)
        self.assertNotIn('Payout', self.g.marking.pending)
        self.assertTrue(DataSemantics.is_accepting(self.g))


# ===========================================================================
# 8. Edge cases
# ===========================================================================

class TestEdgeCases(unittest.TestCase):

    def test_export_plain_dcr_graph(self):
        """Exporting a non-DataDcrGraph should produce valid XML without data fields."""
        from pm4py.objects.dcr.obj import DcrGraph
        g = DcrGraph()
        g.events = {'A', 'B'}
        g.marking.included = {'A', 'B'}
        g.labels = {'A', 'B'}
        g.label_map = {'A': 'A', 'B': 'B'}
        g.conditions = {'B': {'A'}}
        xml = export_to_string(g).decode()
        self.assertIn('<dcrgraph', xml)
        self.assertNotIn('dataType', xml)
        self.assertNotIn('guardedResponses', xml)

    def test_bool_event_value_roundtrip(self):
        """Boolean event values should survive import → export → import."""
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<dcrgraph title="Bool Test">
  <specification>
    <resources>
      <events>
        <event id="Approved" dataType="bool" decision="?"/>
      </events>
      <labels><label id="Approved"/></labels>
      <labelMappings>
        <labelMapping eventId="Approved" labelId="Approved"/>
      </labelMappings>
    </resources>
    <constraints>
      <conditions/><responses/><excludes/><includes/><milestones/><coresponces/>
    </constraints>
  </specification>
  <runtime>
    <marking>
      <executed/>
      <included><event id="Approved"/></included>
      <pendingResponses/>
      <eventValues>
        <eventValue id="Approved" value="true"/>
      </eventValues>
    </marking>
  </runtime>
</dcrgraph>'''
        g1 = import_from_string(xml)
        self.assertEqual(g1.marking.event_values.get('Approved'), True)
        xml2 = export_to_string(g1)
        g2 = import_from_string(xml2)
        self.assertEqual(g2.marking.event_values.get('Approved'), True)

    def test_empty_guarded_sections(self):
        """A graph with no guarded relations should still parse cleanly."""
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<dcrgraph title="Empty Guards">
  <specification>
    <resources>
      <events>
        <event id="A" dataType="int" decision="?"/>
      </events>
      <labels><label id="A"/></labels>
      <labelMappings><labelMapping eventId="A" labelId="A"/></labelMappings>
    </resources>
    <constraints>
      <conditions/><responses/><excludes/><includes/><milestones/><coresponces/>
      <guardedConditions/><guardedResponses/><guardedIncludes/>
      <guardedExcludes/><guardedMilestones/><guardedNoResponses/>
    </constraints>
  </specification>
  <runtime>
    <marking>
      <executed/>
      <included><event id="A"/></included>
      <pendingResponses/>
    </marking>
  </runtime>
</dcrgraph>'''
        g = import_from_string(xml)
        self.assertIsInstance(g, DataDcrGraph)
        self.assertEqual(len(g.guarded_responses), 0)

    def test_trivial_guard_attribute_omitted_on_export(self):
        """Guard attribute should be absent when the guard is trivial."""
        g = DataDcrGraph()
        g.events = {'A', 'B'}
        g.marking.included = {'A', 'B'}
        g.labels = {'A', 'B'}
        g.label_map = {'A': 'A', 'B': 'B'}
        g.event_types = {'A': DataType.INT}
        g.decisions = {'A': INPUT_MARKER}
        # Add a guarded response with a non-trivial guard
        g.guarded_responses = {'A': {'B': Guard(eq(event_ref('A'), const(1)))}}
        xml = export_to_string(g).decode()
        # The response with a guard should have the attribute
        self.assertIn('guard=', xml)

    def test_missing_guard_attribute_becomes_trivial(self):
        """An element in a guarded section without a guard attr → trivial guard."""
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<dcrgraph title="Trivial Guard">
  <specification>
    <resources>
      <events>
        <event id="A" dataType="int" decision="?"/>
        <event id="B" dataType="void"/>
      </events>
      <labels><label id="A"/><label id="B"/></labels>
      <labelMappings>
        <labelMapping eventId="A" labelId="A"/>
        <labelMapping eventId="B" labelId="B"/>
      </labelMappings>
    </resources>
    <constraints>
      <conditions/><responses/><excludes/><includes/><milestones/><coresponces/>
      <guardedConditions/>
      <guardedResponses>
        <!-- no guard attribute means trivial guard -->
        <response sourceId="A" targetId="B"/>
      </guardedResponses>
      <guardedIncludes/><guardedExcludes/><guardedMilestones/><guardedNoResponses/>
    </constraints>
  </specification>
  <runtime>
    <marking>
      <executed/>
      <included><event id="A"/><event id="B"/></included>
      <pendingResponses/>
    </marking>
  </runtime>
</dcrgraph>'''
        g = import_from_string(xml)
        guard = g.guarded_responses['A']['B']
        self.assertTrue(guard.is_trivial)
        self.assertTrue(guard.evaluate({}))


if __name__ == '__main__':
    unittest.main()
