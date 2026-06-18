"""
Execution semantics for data-aware DCR graphs.

Implements the enabling and execution rules from Definitions 3 and 4 of [1]_,
extending the base DCR semantics with:

* **Guard evaluation on conditions and milestones** during enabling checks.
* **Guard evaluation on responses, no-responses, includes, and excludes**
  during event execution.
* **Value computation** for decision events and value storage for input events.

The semantics conservatively extend the base DCR semantics: when all guards are
trivially true and all events are of type void, the behaviour is identical to
standard DCR semantics (Lemma 1 in [1]_).

References
----------
.. [1] Hildebrandt, T.T., Normann, H., Marquard, M., Debois, S., Slaats, T.
   (2022). Decision Modelling in Timed Dynamic Condition Response Graphs with
   Data.  BPM 2021 Workshops, LNBIP 436, pp. 362-374.
"""
from typing import Any, Dict, Optional, Set

from pm4py.objects.dcr.data.expressions import Expression, Guard, INPUT_MARKER
from pm4py.objects.dcr.data.obj import DataDcrGraph
from pm4py.objects.dcr.extended.semantics import ExtendedSemantics


class DataSemantics(ExtendedSemantics):
    """
    Semantics for DCR graphs with data, decisions, and guarded relations.

    All methods are classmethods to stay consistent with the existing
    ``DcrSemantics`` / ``ExtendedSemantics`` API.
    """

    # ------------------------------------------------------------------
    # Guard evaluation helper
    # ------------------------------------------------------------------

    @staticmethod
    def _evaluate_guard(guard: 'Guard', event_values: Dict[str, Any]) -> bool:
        """Safely evaluate a guard, returning ``False`` on missing values."""
        try:
            return guard.evaluate(event_values)
        except (ValueError, KeyError, TypeError):
            return False

    @classmethod
    def _apply_guarded_relation(cls, event: str, guarded_map: Dict,
                                event_values: Dict[str, Any],
                                target_set: Set[str], action: str):
        """Apply a guarded relation effect (add/discard) to a marking set.

        Parameters
        ----------
        event : str
            The event that was just executed.
        guarded_map : dict
            The guarded relation dict (source → {target → Guard}).
        event_values : dict
            Current event values for guard evaluation.
        target_set : set
            The marking set to modify (e.g. ``pending``, ``included``).
        action : 'add' | 'discard'
            Whether to add to or discard from the target set.
        """
        if event not in guarded_map:
            return
        mutate = getattr(target_set, action)
        for target, guard in guarded_map[event].items():
            if cls._evaluate_guard(guard, event_values):
                mutate(target)

    # ------------------------------------------------------------------
    # Enabling (Definition 3)
    # ------------------------------------------------------------------

    @classmethod
    def enabled(cls, graph) -> Set[str]:
        """
        Compute the set of enabled events.

        An event *e* is enabled iff (Definition 3):

        1. *e* is included.
        2. For every included source *e'* with a condition to *e*:
           - If the condition is unguarded: *e'* must have been executed.
           - If the condition is guarded with guard *g*: if *g* evaluates to
             true, then *e'* must have been executed.
        3. For every included source *e'* with a milestone to *e*:
           - If the milestone is unguarded: *e'* must not be pending.
           - If the milestone is guarded with guard *g*: if *g* evaluates to
             true, then *e'* must not be pending.

        Parameters
        ----------
        graph : DataDcrGraph
            The data-aware DCR graph.

        Returns
        -------
        Set[str]
            The set of enabled event identifiers.
        """
        if not isinstance(graph, DataDcrGraph):
            from pm4py.objects.dcr.semantics import DcrSemantics as BaseSem
            return BaseSem.enabled(graph)

        event_values = graph.marking.event_values

        # Start with all included events
        res = set(graph.marking.included)

        # --- Standard (unguarded) conditions (from parent) ---
        for e in set(graph.conditions.keys()).intersection(res):
            if len(graph.conditions[e].intersection(
                    graph.marking.included.difference(graph.marking.executed))) > 0:
                res.discard(e)

        # --- Guarded conditions ---
        for target, sources in graph.guarded_conditions.items():
            if target not in res:
                continue
            for source, guard in sources.items():
                if source not in graph.marking.included:
                    continue
                if cls._evaluate_guard(guard, event_values) and source not in graph.marking.executed:
                    res.discard(target)
                    break

        # --- Standard (unguarded) milestones (from ExtendedDcrGraph) ---
        if hasattr(graph, 'milestones'):
            for e in set(graph.milestones.keys()).intersection(res):
                if len(graph.milestones[e].intersection(
                        graph.marking.included.intersection(graph.marking.pending))) > 0:
                    res.discard(e)

        # --- Guarded milestones ---
        for target, sources in graph.guarded_milestones.items():
            if target not in res:
                continue
            for source, guard in sources.items():
                if source not in graph.marking.included:
                    continue
                if cls._evaluate_guard(guard, event_values) and source in graph.marking.pending:
                    res.discard(target)
                    break

        return res

    # ------------------------------------------------------------------
    # Execution (Definition 4)
    # ------------------------------------------------------------------

    @classmethod
    def execute(cls, graph, event, input_value=None):
        """
        Execute an enabled event, updating the marking.

        For *input events* (``D(e) = ?``), the value is provided via
        ``input_value``.  For *decision events*, the value is computed from
        the event's expression.  For void / untyped events, no value is stored.

        The execution applies all relation effects, evaluating guards where
        present (Definition 4):

        * Remove *event* from pending.
        * Set *event* as executed with its computed/input value.
        * Apply no-response relations (guarded and unguarded).
        * Apply exclude relations (guarded and unguarded).
        * Apply include relations (guarded and unguarded).
        * Apply response relations (guarded and unguarded).

        Parameters
        ----------
        graph : DataDcrGraph
            The data-aware DCR graph (modified in place).
        event : str
            The event identifier to execute.
        input_value : Any, optional
            The value for input events.  Ignored for decision / void events.

        Returns
        -------
        DataDcrGraph
            The graph with updated marking.
        """
        if not isinstance(graph, DataDcrGraph):
            from pm4py.objects.dcr.semantics import DcrSemantics as BaseSem
            return BaseSem.execute(graph, event)

        event_values = graph.marking.event_values

        # --- Compute value (Definition 4, last paragraph) ---
        decision = graph.decisions.get(event)
        if decision == INPUT_MARKER:
            value = input_value
        elif isinstance(decision, Expression):
            value = decision.evaluate(event_values)
        else:
            value = None

        # --- Update executed status and value ---
        graph.marking.pending.discard(event)
        graph.marking.executed.add(event)
        if value is not None:
            event_values[event] = value

        # --- Apply relation effects (unguarded then guarded) ---
        # Order: no-response, exclude, include, response  (Definition 4)

        # No-response
        if hasattr(graph, 'noresponses') and event in graph.noresponses:
            for e_prime in graph.noresponses[event]:
                graph.marking.pending.discard(e_prime)
        cls._apply_guarded_relation(event, graph.guarded_noresponses,
                                    event_values, graph.marking.pending, 'discard')

        # Exclude
        if event in graph.excludes:
            for e_prime in graph.excludes[event]:
                graph.marking.included.discard(e_prime)
        cls._apply_guarded_relation(event, graph.guarded_excludes,
                                    event_values, graph.marking.included, 'discard')

        # Include
        if event in graph.includes:
            for e_prime in graph.includes[event]:
                graph.marking.included.add(e_prime)
        cls._apply_guarded_relation(event, graph.guarded_includes,
                                    event_values, graph.marking.included, 'add')

        # Response
        if event in graph.responses:
            for e_prime in graph.responses[event]:
                graph.marking.pending.add(e_prime)
        cls._apply_guarded_relation(event, graph.guarded_responses,
                                    event_values, graph.marking.pending, 'add')

        return graph

    @classmethod
    def is_accepting(cls, graph) -> bool:
        """
        Check if the graph is in an accepting state.

        The accepting condition is the same as for standard DCR graphs:
        no event is both included and pending.

        Parameters
        ----------
        graph : DataDcrGraph

        Returns
        -------
        bool
        """
        return super().is_accepting(graph)

    # ------------------------------------------------------------------
    # Helper: get event values from marking
    # ------------------------------------------------------------------

    @classmethod
    def get_event_values(cls, graph) -> Dict[str, Any]:
        """Return current event values from the marking."""
        if isinstance(graph, DataDcrGraph):
            return graph.marking.event_values
        return {}
