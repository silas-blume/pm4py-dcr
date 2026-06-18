"""
Example: Data-aware DCR Graph — Expense Report Process

Demonstrates the data-aware DCR graph features based on the expense report
example from [1]_.  This example shows:

1. How to define event types (Int, Bool, Void) and decision expressions.
2. How to set up guarded relations (condition, response, include, exclude,
   milestone, no-response) with boolean guard expressions.
3. How to execute traces with input values and decision computation.
4. How to run conformance checking on data-aware graphs.

The expense report process:
- An employee submits an expense form with a Type (1=cash, 2=bill) and Amount.
- A Decision is computed:
    - Amount < 200 → 1 (direct payout)
    - Amount >= 200 and Type = 2 (bill) → 2 (manager approval required)
    - Amount >= 5000 and Type = 1 (cash) → 3 (rejected)
    - Otherwise → 2 (manager approval required)
- Based on the decision:
    - Decision=1: Payout happens directly.
    - Decision=2: Manager Approval is required, then Payout.
    - Decision=3: Rejected, no payout.

References
----------
.. [1] Hildebrandt et al. (2022). Decision Modelling in Timed Dynamic Condition
   Response Graphs with Data. BPM 2021 Workshops, LNBIP 436, pp. 362-374.
"""
import os
import sys

# ensure the project root is importable when running from the examples/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pm4py.objects.dcr.data.expressions import (
    DataType, Guard, INPUT_MARKER, VoidExpression,
    const, event_ref, eq, lt, ge, not_, and_, if_then_else,
)
from pm4py.objects.dcr.data.obj import DataDcrGraph
from pm4py.objects.dcr.data.semantics import DataSemantics


def build_expense_report_graph():
    """
    Builds the expense report DCR graph with data from the paper (Fig. 2).

    Returns
    -------
    DataDcrGraph
        The expense report process as a data-aware DCR graph.
    """
    g = DataDcrGraph()

    # --- Events ---
    g.events = {'Amount', 'Type', 'Submit', 'Decision', 'Approve', 'Payout'}
    g.labels = {'Amount', 'Type', 'Submit', 'Decision', 'Approve', 'Payout'}
    g.label_map = {e: e for e in g.events}

    # --- Initial marking: all included except Approve ---
    g.marking.included = {'Amount', 'Type', 'Submit', 'Decision', 'Payout'}
    # Approve starts excluded (only included when Decision=2)

    # --- Event types ---
    g.event_types = {
        'Amount': DataType.INT,
        'Type': DataType.INT,
        'Submit': DataType.VOID,
        'Decision': DataType.INT,
        'Approve': DataType.INT,  # 1=approve, 0=reject
        'Payout': DataType.VOID,
    }

    # --- Decision function ---
    # Amount, Type, Approve are input events (value from environment)
    # Decision computes: if Amount<200 then 1 else if (Amount>=200 and Type=2) then 2
    #                    else if (Amount>=5000 and Type=1) then 3 else 2
    decision_expr = if_then_else(
        lt(event_ref('Amount'), const(200)),
        const(1),
        if_then_else(
            and_(ge(event_ref('Amount'), const(200)), eq(event_ref('Type'), const(2))),
            const(2),
            if_then_else(
                and_(ge(event_ref('Amount'), const(5000)), eq(event_ref('Type'), const(1))),
                const(3),
                const(2),
            ),
        ),
    )
    g.decisions = {
        'Amount': INPUT_MARKER,
        'Type': INPUT_MARKER,
        'Submit': VoidExpression(),
        'Decision': decision_expr,
        'Approve': INPUT_MARKER,
        'Payout': VoidExpression(),
    }

    # --- Standard (unguarded) relations ---
    # Conditions: Amount,Type → Submit; Submit → Decision
    g.conditions = {
        'Submit': {'Amount', 'Type'},
        'Decision': {'Submit'},
    }
    # Response: Submit → Decision (decision required same day)
    g.responses = {
        'Submit': {'Decision'},
    }

    # --- Guarded relations ---
    # Response: Decision →[Decision=2] Approve (approval needed)
    # Response: Decision →[not(Decision=3)] Payout (payout expected unless rejected)
    g.guarded_responses = {
        'Decision': {
            'Approve': Guard(eq(event_ref('Decision'), const(2))),
            'Payout': Guard(not_(eq(event_ref('Decision'), const(3)))),
        },
    }

    # No-response: Decision →[Decision=3] Payout (cancel payout obligation if rejected)
    g.guarded_noresponses = {
        'Decision': {
            'Payout': Guard(eq(event_ref('Decision'), const(3))),
        },
    }

    # Include: Decision →[Decision=2] Approve; Approve →[Approve=1] Payout
    g.guarded_includes = {
        'Decision': {
            'Approve': Guard(eq(event_ref('Decision'), const(2))),
        },
        'Approve': {
            'Payout': Guard(eq(event_ref('Approve'), const(1))),
        },
    }

    # Exclude: Decision →[not(Decision=2)] Approve; Approve →[not(Approve=1)] Payout
    g.guarded_excludes = {
        'Decision': {
            'Approve': Guard(not_(eq(event_ref('Decision'), const(2)))),
        },
        'Approve': {
            'Payout': Guard(not_(eq(event_ref('Approve'), const(1)))),
        },
    }

    return g


def simulate_trace(graph, trace, description=""):
    """
    Simulate a trace through a data-aware DCR graph, printing the state
    at each step.

    Parameters
    ----------
    graph : DataDcrGraph
        The DCR graph.
    trace : list of tuple
        Each element is (event_name, input_value_or_None).
    description : str
        Description of the trace.
    """
    print(f"\n{'='*60}")
    print(f"Trace: {description}")
    print(f"{'='*60}")

    for event, value in trace:
        is_input = graph.is_input_event(event)
        is_decision = graph.is_decision_event(event)

        enabled = DataSemantics.enabled(graph)
        status = "ENABLED" if event in enabled else "NOT ENABLED"

        DataSemantics.execute(graph, event, input_value=value)

        computed_val = graph.marking.event_values.get(event, None)
        if is_input:
            print(f"  Execute: {event}?{value} [{status}] → stored value: {computed_val}")
        elif is_decision:
            print(f"  Execute: {event} [{status}] → computed value: {computed_val}")
        else:
            print(f"  Execute: {event} [{status}]")

        print(f"    Included: {sorted(graph.marking.included)}")
        print(f"    Pending:  {sorted(graph.marking.pending)}")
        print(f"    Executed: {sorted(graph.marking.executed)}")

    accepting = DataSemantics.is_accepting(graph)
    print(f"\n  Accepting: {accepting}")
    return accepting


def example_low_cash_expense():
    """
    Trace 1: Low cash expense (Amount=100, Type=1)
    Decision=1 → direct payout, no approval needed.
    """
    g = build_expense_report_graph()
    trace = [
        ('Amount', 100),
        ('Type', 1),
        ('Submit', None),
        ('Decision', None),
        ('Payout', None),
    ]
    accepting = simulate_trace(g, trace, "Low cash expense: Amount=100, Type=1 (cash)")
    assert accepting, "Expected accepting run"


def example_medium_cash_with_approval():
    """
    Trace 2: Medium cash expense (Amount=800, Type=1)
    Decision=2 → manager approval required → approved → payout.
    """
    g = build_expense_report_graph()
    trace = [
        ('Type', 1),
        ('Amount', 800),
        ('Submit', None),
        ('Decision', None),
        ('Approve', 1),   # Manager approves
        ('Payout', None),
    ]
    accepting = simulate_trace(g, trace, "Medium cash: Amount=800, Type=1, Approve=1")
    assert accepting, "Expected accepting run"


def example_high_cash_rejected():
    """
    Trace 3: High cash expense (Amount=6000, Type=1)
    Decision=3 → rejected, no payout.
    """
    g = build_expense_report_graph()
    trace = [
        ('Type', 1),
        ('Amount', 6000),
        ('Submit', None),
        ('Decision', None),
    ]
    accepting = simulate_trace(g, trace, "High cash rejected: Amount=6000, Type=1")
    assert accepting, "Expected accepting run (rejected = no pending obligations)"


def example_conformance_checking():
    """
    Demonstrate conformance checking with data-aware DCR graphs.
    """
    from pm4py.algo.conformance.dcr.variants.classic import RuleBasedConformance

    g = build_expense_report_graph()

    # Create a log with three traces
    log = [
        # Trace 1: Low cash - perfect fit
        [
            {'concept:name': 'Amount', 'data_value': 100},
            {'concept:name': 'Type', 'data_value': 1},
            {'concept:name': 'Submit', 'data_value': None},
            {'concept:name': 'Decision', 'data_value': None},
            {'concept:name': 'Payout', 'data_value': None},
        ],
        # Trace 2: Medium cash, approval needed but never approved - response violation
        [
            {'concept:name': 'Type', 'data_value': 1},
            {'concept:name': 'Amount', 'data_value': 800},
            {'concept:name': 'Submit', 'data_value': None},
            {'concept:name': 'Decision', 'data_value': None},
            # Decision=2 → Approve and Payout are pending, but never fulfilled
        ],
    ]

    parameters = {
        'pm4py:param:activity_key': 'concept:name',
        'data_attribute_key': 'data_value',
    }

    conf = RuleBasedConformance(log, g, parameters=parameters)
    results = conf.apply_conformance()

    print(f"\n{'='*60}")
    print("Conformance Checking Results")
    print(f"{'='*60}")
    for i, result in enumerate(results):
        print(f"\nTrace {i+1}:")
        print(f"  Fitness: {result['dev_fitness']:.2f}")
        print(f"  Is Fit:  {result['is_fit']}")
        if result['deviations']:
            print(f"  Deviations:")
            for dev in result['deviations']:
                print(f"    - {dev}")


if __name__ == '__main__':
    print("=" * 60)
    print("Data-aware DCR Graph: Expense Report Example")
    print("=" * 60)
    print("\nThis example demonstrates decision modelling in DCR graphs")
    print("with data-dependent guards on relations.\n")

    example_low_cash_expense()
    example_medium_cash_with_approval()
    example_high_cash_rejected()
    example_conformance_checking()

    print("\n\nAll examples completed successfully!")
