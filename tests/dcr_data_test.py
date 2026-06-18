"""
Tests for data-aware DCR graphs with decisions and guarded relations.

Tests cover:
1. Expression system (AST construction and evaluation)
2. DataDcrGraph object model
3. DataSemantics (enabling and execution with guards)
4. Conformance checking with data guards
5. The expense report running example from the paper
"""
import os
import sys
import unittest

# Ensure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pm4py.objects.dcr.data.expressions import (
    DataType, Expression, Guard, INPUT_MARKER,
    IntConstant, BoolConstant, EventRef, VoidExpression,
    ArithExpression, ArithOp, CompExpression, CompOp,
    BoolBinaryExpression, BoolOp, NotExpression, IfThenElseExpression,
    const, event_ref, eq, lt, gt, le, ge, add, sub, mul, and_, or_, not_, if_then_else,
)
from pm4py.objects.dcr.data.obj import DataDcrGraph, DataMarking
from pm4py.objects.dcr.data.semantics import DataSemantics
from pm4py.objects.dcr.obj import dcr_template
from copy import deepcopy


# =========================================================================
# 1. Expression tests
# =========================================================================

class TestExpressions(unittest.TestCase):

    def test_int_constant(self):
        expr = IntConstant(42)
        self.assertEqual(expr.evaluate({}), 42)

    def test_bool_constant(self):
        self.assertTrue(BoolConstant(True).evaluate({}))
        self.assertFalse(BoolConstant(False).evaluate({}))

    def test_void_expression(self):
        self.assertIsNone(VoidExpression().evaluate({}))

    def test_event_ref(self):
        vals = {'E1': 100, 'E2': True}
        self.assertEqual(EventRef('E1').evaluate(vals), 100)
        self.assertEqual(EventRef('E2').evaluate(vals), True)

    def test_event_ref_missing_raises(self):
        with self.assertRaises(ValueError):
            EventRef('E_missing').evaluate({})

    def test_arithmetic(self):
        vals = {'E1': 10}
        # E1 + 5
        expr = add(event_ref('E1'), const(5))
        self.assertEqual(expr.evaluate(vals), 15)
        # E1 - 3
        self.assertEqual(sub(event_ref('E1'), const(3)).evaluate(vals), 7)
        # E1 * 2
        self.assertEqual(mul(event_ref('E1'), const(2)).evaluate(vals), 20)

    def test_comparison(self):
        vals = {'E1': 200}
        self.assertTrue(eq(event_ref('E1'), const(200)).evaluate(vals))
        self.assertFalse(eq(event_ref('E1'), const(100)).evaluate(vals))
        self.assertTrue(lt(const(100), event_ref('E1')).evaluate(vals))
        self.assertTrue(gt(event_ref('E1'), const(100)).evaluate(vals))
        self.assertTrue(le(event_ref('E1'), const(200)).evaluate(vals))
        self.assertTrue(ge(event_ref('E1'), const(200)).evaluate(vals))

    def test_boolean_ops(self):
        vals = {'E1': True, 'E2': False}
        self.assertFalse(and_(event_ref('E1'), event_ref('E2')).evaluate(vals))
        self.assertTrue(or_(event_ref('E1'), event_ref('E2')).evaluate(vals))
        self.assertFalse(not_(event_ref('E1')).evaluate(vals))
        self.assertTrue(not_(event_ref('E2')).evaluate(vals))

    def test_if_then_else(self):
        vals = {'E1': 100}
        # if E1 < 200 then 1 else 2
        expr = if_then_else(lt(event_ref('E1'), const(200)), const(1), const(2))
        self.assertEqual(expr.evaluate(vals), 1)

        vals['E1'] = 300
        self.assertEqual(expr.evaluate(vals), 2)

    def test_nested_if_then_else(self):
        """Test the decision expression from the paper's expense report."""
        # Decision logic:
        # if(Amount < 200) then 1
        # else if((Amount >= 200) and Type = 2) then 2
        # else if((Amount >= 5000) and Type = 1) then 3
        # else 2
        decision_expr = if_then_else(
            lt(event_ref('Amount'), const(200)),
            const(1),
            if_then_else(
                and_(ge(event_ref('Amount'), const(200)), eq(event_ref('Type'), const(2))),
                const(2),
                if_then_else(
                    and_(ge(event_ref('Amount'), const(5000)), eq(event_ref('Type'), const(1))),
                    const(3),
                    const(2)
                )
            )
        )

        # Low expense: Amount=100 → 1
        self.assertEqual(decision_expr.evaluate({'Amount': 100, 'Type': 1}), 1)
        # Bill above 200: Amount=800, Type=2 → 2
        self.assertEqual(decision_expr.evaluate({'Amount': 800, 'Type': 2}), 2)
        # High cash: Amount=6000, Type=1 → 3
        self.assertEqual(decision_expr.evaluate({'Amount': 6000, 'Type': 1}), 3)
        # Medium cash: Amount=800, Type=1 → 2
        self.assertEqual(decision_expr.evaluate({'Amount': 800, 'Type': 1}), 2)

    def test_const_helper(self):
        self.assertIsInstance(const(42), IntConstant)
        self.assertIsInstance(const(True), BoolConstant)
        with self.assertRaises(TypeError):
            const("string")

    def test_expression_repr(self):
        expr = add(event_ref('E1'), const(5))
        self.assertIn('E1', repr(expr))
        self.assertIn('5', repr(expr))
        self.assertIn('+', repr(expr))


class TestGuard(unittest.TestCase):

    def test_trivial_guard(self):
        g = Guard()
        self.assertTrue(g.evaluate({}))
        self.assertTrue(g.is_trivial)

    def test_guard_with_expression(self):
        g = Guard(eq(event_ref('E1'), const(2)))
        self.assertFalse(g.is_trivial)
        self.assertTrue(g.evaluate({'E1': 2}))
        self.assertFalse(g.evaluate({'E1': 3}))

    def test_guard_missing_value(self):
        # Guard referencing unexecuted event should return False safely
        g = Guard(eq(event_ref('E_missing'), const(2)))
        # evaluate raises ValueError which Guard.evaluate does not catch
        # (it's caught at the semantics level)
        with self.assertRaises(ValueError):
            g.evaluate({})

    def test_guard_equality(self):
        g1 = Guard(eq(event_ref('E1'), const(2)))
        g2 = Guard(eq(event_ref('E1'), const(2)))
        self.assertEqual(g1, g2)


# =========================================================================
# 2. DataDcrGraph object model tests
# =========================================================================

class TestDataDcrGraph(unittest.TestCase):

    def _make_simple_graph(self):
        """Create a simple data-aware DCR graph for testing."""
        g = DataDcrGraph()
        g.events = {'Amount', 'Type', 'Submit', 'Decision', 'Approve', 'Payout'}
        g.marking.included = {'Amount', 'Type', 'Submit', 'Decision', 'Approve', 'Payout'}
        g.labels = {'Amount', 'Type', 'Submit', 'Decision', 'Approve', 'Payout'}
        g.label_map = {e: e for e in g.events}

        # Types
        g.event_types = {
            'Amount': DataType.INT,
            'Type': DataType.INT,
            'Submit': DataType.VOID,
            'Decision': DataType.INT,
            'Approve': DataType.BOOL,
            'Payout': DataType.VOID,
        }

        # Decisions
        g.decisions = {
            'Amount': INPUT_MARKER,
            'Type': INPUT_MARKER,
            'Submit': VoidExpression(),
            'Decision': if_then_else(
                lt(event_ref('Amount'), const(200)),
                const(1),
                if_then_else(
                    and_(ge(event_ref('Amount'), const(200)), eq(event_ref('Type'), const(2))),
                    const(2),
                    if_then_else(
                        and_(ge(event_ref('Amount'), const(5000)), eq(event_ref('Type'), const(1))),
                        const(3),
                        const(2)
                    )
                )
            ),
            'Approve': INPUT_MARKER,
            'Payout': VoidExpression(),
        }

        # Standard conditions: Amount, Type → Submit; Submit → Decision
        g.conditions = {
            'Submit': {'Amount', 'Type'},
            'Decision': {'Submit'},
        }

        # Standard response: Submit → Decision
        g.responses = {
            'Submit': {'Decision'},
        }

        return g

    def test_create_empty(self):
        g = DataDcrGraph()
        self.assertEqual(len(g.events), 0)
        self.assertEqual(len(g.event_types), 0)
        self.assertEqual(len(g.decisions), 0)
        self.assertEqual(len(g.guarded_conditions), 0)
        self.assertIsInstance(g.marking, DataMarking)

    def test_event_types(self):
        g = self._make_simple_graph()
        self.assertEqual(g.event_types['Amount'], DataType.INT)
        self.assertEqual(g.event_types['Decision'], DataType.INT)
        self.assertEqual(g.event_types['Submit'], DataType.VOID)

    def test_input_decision_events(self):
        g = self._make_simple_graph()
        self.assertTrue(g.is_input_event('Amount'))
        self.assertTrue(g.is_input_event('Type'))
        self.assertTrue(g.is_decision_event('Decision'))
        self.assertFalse(g.is_input_event('Decision'))
        self.assertFalse(g.is_decision_event('Amount'))

    def test_guarded_relations(self):
        g = self._make_simple_graph()
        # Add guarded response: Decision →[Decision=2] Approve
        g.guarded_responses = {
            'Decision': {
                'Approve': Guard(eq(event_ref('Decision'), const(2))),
            }
        }
        self.assertEqual(len(g.guarded_responses), 1)
        self.assertEqual(len(g.guarded_responses['Decision']), 1)

    def test_constraint_count(self):
        g = self._make_simple_graph()
        base = g.get_constraints()

        g.guarded_responses = {
            'Decision': {
                'Approve': Guard(eq(event_ref('Decision'), const(2))),
                'Payout': Guard(not_(eq(event_ref('Decision'), const(3)))),
            }
        }
        self.assertEqual(g.get_constraints(), base + 2)

    def test_obj_to_template(self):
        g = self._make_simple_graph()
        t = g.obj_to_template()
        self.assertIn('eventTypes', t)
        self.assertIn('decisions', t)
        self.assertIn('guardedConditions', t)
        self.assertEqual(t['eventTypes']['Amount'], 'int')

    def test_data_marking(self):
        m = DataMarking()
        self.assertEqual(len(m.event_values), 0)
        m.event_values['E1'] = 42
        self.assertEqual(m.event_values['E1'], 42)

    def test_data_marking_reset(self):
        m = DataMarking()
        m.event_values['E1'] = 42
        m.executed.add('E1')
        m.reset({'executed': set(), 'included': {'E1'}, 'pending': set(), 'eventValues': {}})
        self.assertEqual(len(m.event_values), 0)
        self.assertNotIn('E1', m.executed)


# =========================================================================
# 3. DataSemantics tests
# =========================================================================

class TestDataSemantics(unittest.TestCase):

    def _make_expense_graph(self):
        """
        Creates the expense report DCR graph from the paper's running example (Fig. 2).

        Events: Amount(input int), Type(input int), Submit(void), Decision(decision int),
                Approve(input bool→int), Payout(void)
        """
        g = DataDcrGraph()
        g.events = {'Amount', 'Type', 'Submit', 'Decision', 'Approve', 'Payout'}
        g.marking.included = {'Amount', 'Type', 'Submit', 'Decision', 'Payout'}
        # Approve starts excluded (per the paper)
        g.labels = {'Amount', 'Type', 'Submit', 'Decision', 'Approve', 'Payout'}
        g.label_map = {e: e for e in g.events}

        g.event_types = {
            'Amount': DataType.INT,
            'Type': DataType.INT,
            'Submit': DataType.VOID,
            'Decision': DataType.INT,
            'Approve': DataType.INT,
            'Payout': DataType.VOID,
        }

        # Decision expression from paper
        g.decisions = {
            'Amount': INPUT_MARKER,
            'Type': INPUT_MARKER,
            'Submit': VoidExpression(),
            'Decision': if_then_else(
                lt(event_ref('Amount'), const(200)),
                const(1),
                if_then_else(
                    and_(ge(event_ref('Amount'), const(200)), eq(event_ref('Type'), const(2))),
                    const(2),
                    if_then_else(
                        and_(ge(event_ref('Amount'), const(5000)), eq(event_ref('Type'), const(1))),
                        const(3),
                        const(2)
                    )
                )
            ),
            'Approve': INPUT_MARKER,
            'Payout': VoidExpression(),
        }

        # Standard conditions: Amount, Type → Submit; Submit → Decision
        g.conditions = {
            'Submit': {'Amount', 'Type'},
            'Decision': {'Submit'},
        }

        # Standard response: Submit → Decision
        g.responses = {
            'Submit': {'Decision'},
        }

        # Guarded response: Decision →[Decision=2] Approve (if approval needed)
        # Guarded response: Decision →[not(Decision=3)] Payout (if not rejected)
        g.guarded_responses = {
            'Decision': {
                'Approve': Guard(eq(event_ref('Decision'), const(2))),
                'Payout': Guard(not_(eq(event_ref('Decision'), const(3)))),
            }
        }

        # Guarded no-response: Decision →[Decision=3] Payout (if rejected, remove pending)
        g.guarded_noresponses = {
            'Decision': {
                'Payout': Guard(eq(event_ref('Decision'), const(3))),
            }
        }

        # Guarded include: Decision →[Decision=2] Approve
        g.guarded_includes = {
            'Decision': {
                'Approve': Guard(eq(event_ref('Decision'), const(2))),
            },
            'Approve': {
                'Payout': Guard(eq(event_ref('Approve'), const(1))),
            }
        }

        # Guarded exclude: Decision →[not(Decision=2)] Approve
        g.guarded_excludes = {
            'Decision': {
                'Approve': Guard(not_(eq(event_ref('Decision'), const(2)))),
            },
            'Approve': {
                'Payout': Guard(not_(eq(event_ref('Approve'), const(1)))),
            }
        }

        return g

    # --- Enabling tests ---

    def test_initial_enabled(self):
        """Initially only Amount and Type should be enabled (no conditions on them)."""
        g = self._make_expense_graph()
        enabled = DataSemantics.enabled(g)
        self.assertIn('Amount', enabled)
        self.assertIn('Type', enabled)
        self.assertNotIn('Submit', enabled)  # blocked by conditions on Amount, Type
        self.assertNotIn('Decision', enabled)  # blocked by condition on Submit

    def test_enabled_after_inputs(self):
        """After executing Amount and Type, Submit should be enabled."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Amount', input_value=100)
        DataSemantics.execute(g, 'Type', input_value=1)
        enabled = DataSemantics.enabled(g)
        self.assertIn('Submit', enabled)
        self.assertNotIn('Decision', enabled)

    def test_enabled_after_submit(self):
        """After Submit, Decision should be enabled."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Amount', input_value=100)
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Submit')
        enabled = DataSemantics.enabled(g)
        self.assertIn('Decision', enabled)

    # --- Execution with data flow tests ---

    def test_input_event_stores_value(self):
        """Input events should store their value in the marking."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Amount', input_value=100)
        self.assertEqual(g.marking.event_values['Amount'], 100)

    def test_decision_event_computes_value(self):
        """Decision events compute their value from the expression."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Amount', input_value=100)
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')
        # Amount < 200 → Decision = 1
        self.assertEqual(g.marking.event_values['Decision'], 1)

    def test_decision_medium_cash(self):
        """Medium cash expense: Amount=800, Type=1 → Decision=2."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Amount', input_value=800)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')
        self.assertEqual(g.marking.event_values['Decision'], 2)

    def test_decision_high_cash_reject(self):
        """High cash: Amount=6000, Type=1 → Decision=3."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Amount', input_value=6000)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')
        self.assertEqual(g.marking.event_values['Decision'], 3)

    def test_decision_bill_above_200(self):
        """Bill above 200: Amount=800, Type=2 → Decision=2."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Type', input_value=2)
        DataSemantics.execute(g, 'Amount', input_value=800)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')
        self.assertEqual(g.marking.event_values['Decision'], 2)

    # --- Guarded response tests ---

    def test_guarded_response_low_expense(self):
        """Low expense (Decision=1): Payout should be pending, Approve should not."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Amount', input_value=100)
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')

        # Decision=1: not(Decision=3) is true → Payout is pending
        self.assertIn('Payout', g.marking.pending)
        # Decision=1: Decision=2 is false → Approve is NOT pending
        self.assertNotIn('Approve', g.marking.pending)

    def test_guarded_response_medium_cash(self):
        """Medium cash (Decision=2): both Approve and Payout should be pending."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Amount', input_value=800)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')

        self.assertIn('Approve', g.marking.pending)
        self.assertIn('Payout', g.marking.pending)

    def test_guarded_noresponse_rejection(self):
        """High cash (Decision=3): Payout should NOT be pending (no-response cancels it)."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Amount', input_value=6000)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')

        # Decision=3: no-response guard (Decision=3) is true → remove Payout from pending
        # Also response guard not(Decision=3) is false → Payout not added to pending
        self.assertNotIn('Payout', g.marking.pending)

    # --- Guarded include/exclude tests ---

    def test_guarded_include_approve(self):
        """Decision=2 should include Approve."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Amount', input_value=800)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')
        self.assertIn('Approve', g.marking.included)

    def test_guarded_exclude_approve(self):
        """Decision=1 (not 2) should exclude Approve."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Amount', input_value=100)
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')
        self.assertNotIn('Approve', g.marking.included)

    def test_guarded_include_payout_after_approve(self):
        """Approve=1 should include Payout."""
        g = self._make_expense_graph()
        g.marking.included.add('Approve')  # manually include for this test
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Amount', input_value=800)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')
        DataSemantics.execute(g, 'Approve', input_value=1)
        self.assertIn('Payout', g.marking.included)

    def test_guarded_exclude_payout_after_reject_approve(self):
        """Approve != 1 should exclude Payout."""
        g = self._make_expense_graph()
        g.marking.included.add('Approve')
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Amount', input_value=800)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')
        DataSemantics.execute(g, 'Approve', input_value=0)
        self.assertNotIn('Payout', g.marking.included)

    # --- Full trace tests (from paper Section 2.3) ---

    def test_trace_low_cash_expense(self):
        """
        Trace 1 from paper: Amount?100, Type?1, Submit, Decision, Payout
        Low expense → direct payout.
        """
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Amount', input_value=100)
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')
        # Decision=1 → Payout pending, Approve excluded
        self.assertNotIn('Approve', g.marking.included)
        self.assertIn('Payout', g.marking.pending)
        DataSemantics.execute(g, 'Payout')
        # After payout, should be accepting
        self.assertTrue(DataSemantics.is_accepting(g))

    def test_trace_medium_cash_approved(self):
        """
        Trace 2 from paper: Type?1, Amount?800, Submit, Decision, Approve?1, Payout
        Medium cash → needs manager approval → approved → payout.
        """
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Amount', input_value=800)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')
        # Decision=2 → Approve included and pending
        self.assertIn('Approve', g.marking.included)
        self.assertIn('Approve', g.marking.pending)
        DataSemantics.execute(g, 'Approve', input_value=1)
        # Approve=1 → Payout included
        self.assertIn('Payout', g.marking.included)
        DataSemantics.execute(g, 'Payout')
        self.assertTrue(DataSemantics.is_accepting(g))

    def test_trace_high_cash_rejected(self):
        """
        Trace 3 from paper: Type?1, Amount?6000, Submit, Decision
        High cash → rejected, process stops (no payout possible).
        """
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Amount', input_value=6000)
        DataSemantics.execute(g, 'Submit')
        DataSemantics.execute(g, 'Decision')
        # Decision=3 → Payout not pending (no-response), Approve excluded
        self.assertNotIn('Approve', g.marking.included)
        self.assertNotIn('Payout', g.marking.pending)
        # Should be accepting (no included pending events)
        self.assertTrue(DataSemantics.is_accepting(g))

    def test_trace_not_accepting_when_pending(self):
        """After Submit (which triggers response to Decision), graph is not accepting."""
        g = self._make_expense_graph()
        DataSemantics.execute(g, 'Amount', input_value=100)
        DataSemantics.execute(g, 'Type', input_value=1)
        DataSemantics.execute(g, 'Submit')
        # Decision is pending and included
        self.assertIn('Decision', g.marking.pending)
        self.assertFalse(DataSemantics.is_accepting(g))

    # --- Guarded condition tests ---

    def test_guarded_condition_blocks_when_true(self):
        """A guarded condition with true guard should block the target."""
        g = DataDcrGraph()
        g.events = {'A', 'B', 'C'}
        g.marking.included = {'A', 'B', 'C'}
        g.labels = {'A', 'B', 'C'}
        g.label_map = {e: e for e in g.events}
        g.event_types = {'A': DataType.INT, 'B': DataType.VOID, 'C': DataType.VOID}
        g.decisions = {'A': INPUT_MARKER}

        # Guarded condition: B →[A=1] C (C requires B executed, but only if A=1)
        g.guarded_conditions = {
            'C': {'B': Guard(eq(event_ref('A'), const(1)))}
        }

        # Execute A with value 1
        DataSemantics.execute(g, 'A', input_value=1)
        enabled = DataSemantics.enabled(g)
        # C should be blocked because guard is true and B not executed
        self.assertNotIn('C', enabled)
        self.assertIn('B', enabled)

        # Now execute B
        DataSemantics.execute(g, 'B')
        enabled = DataSemantics.enabled(g)
        self.assertIn('C', enabled)

    def test_guarded_condition_inactive_when_false(self):
        """A guarded condition with false guard should not block the target."""
        g = DataDcrGraph()
        g.events = {'A', 'B', 'C'}
        g.marking.included = {'A', 'B', 'C'}
        g.labels = {'A', 'B', 'C'}
        g.label_map = {e: e for e in g.events}
        g.event_types = {'A': DataType.INT, 'B': DataType.VOID, 'C': DataType.VOID}
        g.decisions = {'A': INPUT_MARKER}

        # Guarded condition: B →[A=1] C
        g.guarded_conditions = {
            'C': {'B': Guard(eq(event_ref('A'), const(1)))}
        }

        # Execute A with value 2 (guard false)
        DataSemantics.execute(g, 'A', input_value=2)
        enabled = DataSemantics.enabled(g)
        # C should NOT be blocked because guard is false
        self.assertIn('C', enabled)

    def test_guarded_milestone_blocks(self):
        """A guarded milestone with true guard blocks target if source is pending."""
        g = DataDcrGraph()
        g.events = {'A', 'B', 'C'}
        g.marking.included = {'A', 'B', 'C'}
        g.marking.pending = {'B'}  # B is pending
        g.labels = {'A', 'B', 'C'}
        g.label_map = {e: e for e in g.events}
        g.event_types = {'A': DataType.INT, 'B': DataType.VOID, 'C': DataType.VOID}
        g.decisions = {'A': INPUT_MARKER}

        # Guarded milestone: B →[A=1] C (C blocked by B if A=1 and B is pending)
        g.guarded_milestones = {
            'C': {'B': Guard(eq(event_ref('A'), const(1)))}
        }

        DataSemantics.execute(g, 'A', input_value=1)
        enabled = DataSemantics.enabled(g)
        # C blocked: guard true, B is pending and included
        self.assertNotIn('C', enabled)

    def test_guarded_milestone_inactive(self):
        """A guarded milestone with false guard does not block."""
        g = DataDcrGraph()
        g.events = {'A', 'B', 'C'}
        g.marking.included = {'A', 'B', 'C'}
        g.marking.pending = {'B'}
        g.labels = {'A', 'B', 'C'}
        g.label_map = {e: e for e in g.events}
        g.event_types = {'A': DataType.INT, 'B': DataType.VOID, 'C': DataType.VOID}
        g.decisions = {'A': INPUT_MARKER}

        g.guarded_milestones = {
            'C': {'B': Guard(eq(event_ref('A'), const(1)))}
        }

        DataSemantics.execute(g, 'A', input_value=2)  # guard false
        enabled = DataSemantics.enabled(g)
        self.assertIn('C', enabled)


# =========================================================================
# 4. Conformance checking tests
# =========================================================================

class TestDataConformance(unittest.TestCase):

    def _make_simple_data_graph(self):
        """Simple graph: A(input int) → B(void), with guarded response A →[A>=100] C."""
        g = DataDcrGraph()
        g.events = {'A', 'B', 'C'}
        g.marking.included = {'A', 'B', 'C'}
        g.labels = {'A', 'B', 'C'}
        g.label_map = {e: e for e in g.events}

        g.event_types = {
            'A': DataType.INT,
            'B': DataType.VOID,
            'C': DataType.VOID,
        }
        g.decisions = {'A': INPUT_MARKER}

        # Standard condition: A → B
        g.conditions = {'B': {'A'}}
        # Guarded response: A →[A>=100] C
        g.guarded_responses = {
            'A': {'C': Guard(ge(event_ref('A'), const(100)))}
        }

        return g

    def test_conformance_fit_trace(self):
        """A trace that satisfies all constraints should be fit."""
        from pm4py.algo.conformance.dcr.variants.classic import RuleBasedConformance

        g = self._make_simple_data_graph()
        # Trace: A(value=50), B — A < 100 so no guarded response, B condition met
        log = [
            [{'concept:name': 'A', 'data_value': 50}, {'concept:name': 'B', 'data_value': None}]
        ]
        parameters = {
            'pm4py:param:activity_key': 'concept:name',
            'data_attribute_key': 'data_value',
        }

        conf = RuleBasedConformance(log, g, parameters=parameters)
        results = conf.apply_conformance()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['is_fit'])

    def test_conformance_guarded_response_violation(self):
        """A trace that triggers guarded response but doesn't fulfill it."""
        from pm4py.algo.conformance.dcr.variants.classic import RuleBasedConformance

        g = self._make_simple_data_graph()
        # Trace: A(value=200), B — A >= 100 so C becomes pending, but C never executed
        log = [
            [{'concept:name': 'A', 'data_value': 200}, {'concept:name': 'B', 'data_value': None}]
        ]
        parameters = {
            'pm4py:param:activity_key': 'concept:name',
            'data_attribute_key': 'data_value',
        }

        conf = RuleBasedConformance(log, g, parameters=parameters)
        results = conf.apply_conformance()
        self.assertEqual(len(results), 1)
        # C should be pending and included → not accepting → response violation
        self.assertFalse(results[0]['is_fit'])

    def test_conformance_guarded_response_fulfilled(self):
        """A trace that triggers and fulfills the guarded response."""
        from pm4py.algo.conformance.dcr.variants.classic import RuleBasedConformance

        g = self._make_simple_data_graph()
        # Trace: A(value=200), B, C — C satisfies the guarded response
        log = [
            [
                {'concept:name': 'A', 'data_value': 200},
                {'concept:name': 'B', 'data_value': None},
                {'concept:name': 'C', 'data_value': None},
            ]
        ]
        parameters = {
            'pm4py:param:activity_key': 'concept:name',
            'data_attribute_key': 'data_value',
        }

        conf = RuleBasedConformance(log, g, parameters=parameters)
        results = conf.apply_conformance()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['is_fit'])


# =========================================================================
# 5. Backward compatibility tests
# =========================================================================

class TestBackwardCompatibility(unittest.TestCase):
    """Ensure that DataSemantics works correctly on non-data DCR graphs."""

    def test_semantics_on_base_graph(self):
        """DataSemantics should fall back to ExtendedSemantics for base graphs."""
        from pm4py.objects.dcr.obj import DcrGraph
        g = DcrGraph()
        g.events = {'A', 'B'}
        g.marking.included = {'A', 'B'}
        g.conditions = {'B': {'A'}}

        enabled = DataSemantics.enabled(g)
        self.assertIn('A', enabled)
        self.assertNotIn('B', enabled)

        DataSemantics.execute(g, 'A')
        enabled = DataSemantics.enabled(g)
        self.assertIn('B', enabled)

    def test_base_template_has_data_fields(self):
        """The dcr_template should include data fields for forward compatibility."""
        self.assertIn('eventTypes', dcr_template)
        self.assertIn('decisions', dcr_template)
        self.assertIn('guardedConditions', dcr_template)
        self.assertIn('eventValues', dcr_template['marking'])


# =========================================================================
# 6. Edge case tests
# =========================================================================

class TestEdgeCases(unittest.TestCase):

    def test_multiple_guarded_conditions_same_target(self):
        """Multiple guarded conditions on the same target event."""
        g = DataDcrGraph()
        g.events = {'X', 'Y', 'Z', 'T'}
        g.marking.included = {'X', 'Y', 'Z', 'T'}
        g.labels = g.events.copy()
        g.label_map = {e: e for e in g.events}
        g.event_types = {'X': DataType.INT, 'Y': DataType.VOID, 'Z': DataType.VOID, 'T': DataType.VOID}
        g.decisions = {'X': INPUT_MARKER}

        # T has two guarded conditions: Y →[X>0] T and Z →[X>0] T
        g.guarded_conditions = {
            'T': {
                'Y': Guard(gt(event_ref('X'), const(0))),
                'Z': Guard(gt(event_ref('X'), const(0))),
            }
        }

        DataSemantics.execute(g, 'X', input_value=5)
        # Both Y and Z must be executed for T to be enabled
        self.assertNotIn('T', DataSemantics.enabled(g))
        DataSemantics.execute(g, 'Y')
        self.assertNotIn('T', DataSemantics.enabled(g))
        DataSemantics.execute(g, 'Z')
        self.assertIn('T', DataSemantics.enabled(g))

    def test_void_events_no_data(self):
        """Void events should work normally without data."""
        g = DataDcrGraph()
        g.events = {'A', 'B'}
        g.marking.included = {'A', 'B'}
        g.labels = {'A', 'B'}
        g.label_map = {e: e for e in g.events}
        g.event_types = {'A': DataType.VOID, 'B': DataType.VOID}

        DataSemantics.execute(g, 'A')
        self.assertIn('A', g.marking.executed)
        self.assertNotIn('A', g.marking.event_values)  # void → no value stored

    def test_overwrite_event_value(self):
        """Re-executing an input event should overwrite its stored value."""
        g = DataDcrGraph()
        g.events = {'A'}
        g.marking.included = {'A'}
        g.labels = {'A'}
        g.label_map = {'A': 'A'}
        g.event_types = {'A': DataType.INT}
        g.decisions = {'A': INPUT_MARKER}

        DataSemantics.execute(g, 'A', input_value=10)
        self.assertEqual(g.marking.event_values['A'], 10)

        DataSemantics.execute(g, 'A', input_value=20)
        self.assertEqual(g.marking.event_values['A'], 20)

    def test_complex_guard_expression(self):
        """Test a complex nested guard expression."""
        # Guard: (A > 10 and A < 100) or B = True
        guard = Guard(
            or_(
                and_(gt(event_ref('A'), const(10)), lt(event_ref('A'), const(100))),
                eq(event_ref('B'), const(True))
            )
        )
        self.assertTrue(guard.evaluate({'A': 50, 'B': False}))   # first clause true
        self.assertTrue(guard.evaluate({'A': 5, 'B': True}))     # second clause true
        self.assertFalse(guard.evaluate({'A': 5, 'B': False}))   # both false
        self.assertTrue(guard.evaluate({'A': 50, 'B': True}))    # both true

    def test_guarded_and_unguarded_same_relation(self):
        """Both guarded and unguarded responses from the same source."""
        g = DataDcrGraph()
        g.events = {'A', 'B', 'C'}
        g.marking.included = {'A', 'B', 'C'}
        g.labels = g.events.copy()
        g.label_map = {e: e for e in g.events}
        g.event_types = {'A': DataType.INT, 'B': DataType.VOID, 'C': DataType.VOID}
        g.decisions = {'A': INPUT_MARKER}

        # Unguarded response: A → B (always)
        g.responses = {'A': {'B'}}
        # Guarded response: A →[A>100] C (only if A > 100)
        g.guarded_responses = {'A': {'C': Guard(gt(event_ref('A'), const(100)))}}

        DataSemantics.execute(g, 'A', input_value=50)
        self.assertIn('B', g.marking.pending)      # unguarded → always
        self.assertNotIn('C', g.marking.pending)    # guarded → false

    def test_guarded_and_unguarded_same_relation_guard_true(self):
        """Both guarded and unguarded responses, guard is true."""
        g = DataDcrGraph()
        g.events = {'A', 'B', 'C'}
        g.marking.included = {'A', 'B', 'C'}
        g.labels = g.events.copy()
        g.label_map = {e: e for e in g.events}
        g.event_types = {'A': DataType.INT, 'B': DataType.VOID, 'C': DataType.VOID}
        g.decisions = {'A': INPUT_MARKER}

        g.responses = {'A': {'B'}}
        g.guarded_responses = {'A': {'C': Guard(gt(event_ref('A'), const(100)))}}

        DataSemantics.execute(g, 'A', input_value=200)
        self.assertIn('B', g.marking.pending)
        self.assertIn('C', g.marking.pending)


if __name__ == '__main__':
    unittest.main()


# =========================================================================
# 7. Additional coverage tests
# =========================================================================

class TestTemplateRoundTrip(unittest.TestCase):
    """Verify that obj_to_template / constructor round-trip is lossless."""

    def test_round_trip_preserves_graph(self):
        g = DataDcrGraph()
        g.events = {'A', 'B'}
        g.marking.included = {'A', 'B'}
        g.labels = {'A', 'B'}
        g.label_map = {'A': 'A', 'B': 'B'}
        g.event_types = {'A': DataType.INT, 'B': DataType.VOID}
        g.decisions = {'A': INPUT_MARKER}
        g.conditions = {'B': {'A'}}
        g.guarded_responses = {'A': {'B': Guard(gt(event_ref('A'), const(0)))}}

        DataSemantics.execute(g, 'A', input_value=42)

        template = g.obj_to_template()
        g2 = DataDcrGraph(template)

        self.assertEqual(g2.event_types['A'], DataType.INT)
        self.assertIn('eventValues', template['marking'])
        self.assertEqual(template['marking']['eventValues'].get('A'), 42)

    def test_template_has_all_guarded_keys(self):
        g = DataDcrGraph()
        g.events = {'A'}
        g.marking.included = {'A'}
        g.labels = {'A'}
        g.label_map = {'A': 'A'}
        t = g.obj_to_template()
        for key in ('guardedConditions', 'guardedResponses', 'guardedIncludes',
                     'guardedExcludes', 'guardedMilestones', 'guardedNoResponses'):
            self.assertIn(key, t)


class TestDataMarkingRepr(unittest.TestCase):

    def test_repr_contains_event_values(self):
        m = DataMarking()
        m.event_values['X'] = 99
        r = repr(m)
        self.assertIn('event_values', r)
        self.assertIn('99', r)


class TestGetEventValues(unittest.TestCase):

    def test_returns_values_for_data_graph(self):
        g = DataDcrGraph()
        g.events = {'A'}
        g.marking.included = {'A'}
        g.labels = {'A'}
        g.label_map = {'A': 'A'}
        g.event_types = {'A': DataType.INT}
        g.decisions = {'A': INPUT_MARKER}
        DataSemantics.execute(g, 'A', input_value=7)
        vals = DataSemantics.get_event_values(g)
        self.assertEqual(vals['A'], 7)

    def test_returns_empty_for_base_graph(self):
        from pm4py.objects.dcr.obj import DcrGraph
        g = DcrGraph()
        vals = DataSemantics.get_event_values(g)
        self.assertEqual(vals, {})


class TestEvaluateGuardHelper(unittest.TestCase):
    """Test the _evaluate_guard static method directly."""

    def test_true_guard(self):
        g = Guard(eq(event_ref('A'), const(1)))
        self.assertTrue(DataSemantics._evaluate_guard(g, {'A': 1}))

    def test_false_guard(self):
        g = Guard(eq(event_ref('A'), const(1)))
        self.assertFalse(DataSemantics._evaluate_guard(g, {'A': 2}))

    def test_missing_ref_returns_false(self):
        g = Guard(eq(event_ref('MISSING'), const(1)))
        self.assertFalse(DataSemantics._evaluate_guard(g, {}))


class TestDataDcrGraphEquality(unittest.TestCase):

    def test_equal_graphs(self):
        g1 = DataDcrGraph()
        g1.events = {'A'}
        g1.marking.included = {'A'}
        g1.event_types = {'A': DataType.INT}

        g2 = DataDcrGraph()
        g2.events = {'A'}
        g2.marking.included = {'A'}
        g2.event_types = {'A': DataType.INT}

        self.assertEqual(g1, g2)

    def test_unequal_types(self):
        g1 = DataDcrGraph()
        g1.events = {'A'}
        g1.event_types = {'A': DataType.INT}

        g2 = DataDcrGraph()
        g2.events = {'A'}
        g2.event_types = {'A': DataType.BOOL}

        self.assertNotEqual(g1, g2)

    def test_unequal_guarded_relations(self):
        g1 = DataDcrGraph()
        g1.events = {'A', 'B'}

        g2 = DataDcrGraph()
        g2.events = {'A', 'B'}
        g2.guarded_responses = {'A': {'B': Guard(eq(event_ref('A'), const(1)))}}

        self.assertNotEqual(g1, g2)

    def test_not_equal_to_non_data_graph(self):
        from pm4py.objects.dcr.obj import DcrGraph
        g1 = DataDcrGraph()
        g2 = DcrGraph()
        self.assertNotEqual(g1, g2)


class TestChainedDecisions(unittest.TestCase):
    """Decision event referencing another decision event's value."""

    def test_chained_decision_evaluation(self):
        g = DataDcrGraph()
        g.events = {'A', 'D1', 'D2'}
        g.marking.included = {'A', 'D1', 'D2'}
        g.labels = g.events.copy()
        g.label_map = {e: e for e in g.events}
        g.event_types = {'A': DataType.INT, 'D1': DataType.INT, 'D2': DataType.INT}
        # A is input, D1 = A * 2, D2 = D1 + 10
        g.decisions = {
            'A': INPUT_MARKER,
            'D1': mul(event_ref('A'), const(2)),
            'D2': add(event_ref('D1'), const(10)),
        }

        DataSemantics.execute(g, 'A', input_value=5)
        DataSemantics.execute(g, 'D1')
        self.assertEqual(g.marking.event_values['D1'], 10)  # 5 * 2
        DataSemantics.execute(g, 'D2')
        self.assertEqual(g.marking.event_values['D2'], 20)  # 10 + 10


class TestConformanceConditionViolation(unittest.TestCase):
    """Conformance checking with data-condition violations."""

    def test_guarded_condition_violation_detected(self):
        from pm4py.algo.conformance.dcr.variants.classic import RuleBasedConformance

        g = DataDcrGraph()
        g.events = {'A', 'B', 'C'}
        g.marking.included = {'A', 'B', 'C'}
        g.labels = {'A', 'B', 'C'}
        g.label_map = {e: e for e in g.events}
        g.event_types = {'A': DataType.INT, 'B': DataType.VOID, 'C': DataType.VOID}
        g.decisions = {'A': INPUT_MARKER}
        # Guarded condition: B →[A=1] C  (C requires B if A=1)
        g.guarded_conditions = {'C': {'B': Guard(eq(event_ref('A'), const(1)))}}

        # Trace: A(1), C — C executed without B, but guard is true → violation
        log = [
            [{'concept:name': 'A', 'data_value': 1}, {'concept:name': 'C'}]
        ]
        parameters = {
            'pm4py:param:activity_key': 'concept:name',
            'data_attribute_key': 'data_value',
        }

        conf = RuleBasedConformance(log, g, parameters=parameters)
        results = conf.apply_conformance()
        self.assertFalse(results[0]['is_fit'])
        deviation_types = [d[0] for d in results[0]['deviations']]
        self.assertIn('dataConditionViolation', deviation_types)

    def test_guarded_condition_no_violation_when_guard_false(self):
        from pm4py.algo.conformance.dcr.variants.classic import RuleBasedConformance

        g = DataDcrGraph()
        g.events = {'A', 'B', 'C'}
        g.marking.included = {'A', 'B', 'C'}
        g.labels = {'A', 'B', 'C'}
        g.label_map = {e: e for e in g.events}
        g.event_types = {'A': DataType.INT, 'B': DataType.VOID, 'C': DataType.VOID}
        g.decisions = {'A': INPUT_MARKER}
        g.guarded_conditions = {'C': {'B': Guard(eq(event_ref('A'), const(1)))}}

        # Trace: A(2), C — guard is false, so no violation from guarded condition
        log = [
            [{'concept:name': 'A', 'data_value': 2}, {'concept:name': 'C'}]
        ]
        parameters = {
            'pm4py:param:activity_key': 'concept:name',
            'data_attribute_key': 'data_value',
        }

        conf = RuleBasedConformance(log, g, parameters=parameters)
        results = conf.apply_conformance()
        deviation_types = [d[0] for d in results[0]['deviations']]
        self.assertNotIn('dataConditionViolation', deviation_types)


class TestMultipleTraceConformance(unittest.TestCase):
    """Conformance checking across multiple traces."""

    def test_multiple_traces(self):
        from pm4py.algo.conformance.dcr.variants.classic import RuleBasedConformance

        g = DataDcrGraph()
        g.events = {'A', 'B'}
        g.marking.included = {'A', 'B'}
        g.labels = {'A', 'B'}
        g.label_map = {e: e for e in g.events}
        g.event_types = {'A': DataType.INT, 'B': DataType.VOID}
        g.decisions = {'A': INPUT_MARKER}
        g.guarded_responses = {'A': {'B': Guard(ge(event_ref('A'), const(10)))}}

        log = [
            # Trace 1: A(5), no guarded response triggered → fit
            [{'concept:name': 'A', 'data_value': 5}],
            # Trace 2: A(20), B becomes pending but never executed → not fit
            [{'concept:name': 'A', 'data_value': 20}],
            # Trace 3: A(20), B → guarded response fulfilled → fit
            [{'concept:name': 'A', 'data_value': 20}, {'concept:name': 'B'}],
        ]
        parameters = {
            'pm4py:param:activity_key': 'concept:name',
            'data_attribute_key': 'data_value',
        }

        conf = RuleBasedConformance(log, g, parameters=parameters)
        results = conf.apply_conformance()
        self.assertEqual(len(results), 3)
        self.assertTrue(results[0]['is_fit'])
        self.assertFalse(results[1]['is_fit'])
        self.assertTrue(results[2]['is_fit'])


class TestExpressionEquality(unittest.TestCase):
    """Expression __eq__ via repr comparison."""

    def test_equal_expressions(self):
        e1 = add(event_ref('A'), const(5))
        e2 = add(event_ref('A'), const(5))
        self.assertEqual(e1, e2)

    def test_unequal_expressions(self):
        e1 = add(event_ref('A'), const(5))
        e2 = sub(event_ref('A'), const(5))
        self.assertNotEqual(e1, e2)

    def test_not_equal_to_non_expression(self):
        e1 = const(5)
        self.assertNotEqual(e1, "not an expression")
