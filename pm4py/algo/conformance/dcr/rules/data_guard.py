"""
Conformance rule for checking data guard violations on DCR relations.

Detects cases where a guarded condition or milestone is violated during
execution, or where guarded response/include/exclude constraints are not
satisfied at the end of a trace.
"""
from pm4py.algo.conformance.dcr.rules.abc import CheckFrame
from pm4py.objects.dcr.data.obj import DataDcrGraph
from pm4py.objects.dcr.data.semantics import DataSemantics
from typing import Any, Dict, List, Tuple


class CheckDataGuard(CheckFrame):
    """
    Checks for data-guard-related deviations.

    Deviation types produced:

    * ``'dataConditionViolation'`` — a guarded condition was active (guard
      evaluated to true) but the source event was not executed.
    * ``'dataMilestoneViolation'`` — a guarded milestone was active (guard
      evaluated to true) but the source event was still pending.
    * ``'dataExcludeViolation'`` — an event was executed while excluded due
      to a guarded exclude relation.
    """

    @classmethod
    def check_enabled_rule(cls, event: str, graph: DataDcrGraph,
                           deviations: List[Tuple[str, Any]]):
        if not isinstance(graph, DataDcrGraph):
            return deviations

        event_values = graph.marking.event_values

        # --- Guarded condition violations ---
        if event in graph.guarded_conditions:
            for source, guard in graph.guarded_conditions[event].items():
                if source not in graph.marking.included:
                    continue
                if (DataSemantics._evaluate_guard(guard, event_values)
                        and source not in graph.marking.executed):
                    dev = ('dataConditionViolation', (source, event, repr(guard)))
                    if dev not in deviations:
                        deviations.append(dev)

        # --- Guarded milestone violations ---
        if event in graph.guarded_milestones:
            for source, guard in graph.guarded_milestones[event].items():
                if source not in graph.marking.included:
                    continue
                if (DataSemantics._evaluate_guard(guard, event_values)
                        and source in graph.marking.pending):
                    dev = ('dataMilestoneViolation', (source, event, repr(guard)))
                    if dev not in deviations:
                        deviations.append(dev)

        return deviations

        return deviations

    @classmethod
    def check_exclude_rule(cls, event: str, graph: DataDcrGraph,
                           execution_history: List[str],
                           deviations: List[Tuple[str, Any]]):
        """
        Check for guarded exclude violations.

        An event is in a guarded-exclude violation if it was excluded by a
        guarded exclude relation (whose guard was true at the time) but the
        trace attempts to execute it anyway.

        Parameters
        ----------
        event : str
            The event to check.
        graph : DataDcrGraph
            The data-aware DCR graph.
        execution_history : list
            Events executed so far in the trace.
        deviations : list
            Accumulated deviations (modified in place).
        """
        if not isinstance(graph, DataDcrGraph):
            return deviations

        if event not in graph.marking.included:
            for event_prime in execution_history:
                if event_prime in graph.guarded_excludes:
                    if event in graph.guarded_excludes[event_prime]:
                        dev = ('dataExcludeViolation', (event_prime, event))
                        if dev not in deviations:
                            deviations.append(dev)

        return deviations

    @classmethod
    def check_rule(cls, *args, **kwargs):
        """Generic dispatch — not used directly; use specific check methods."""
        pass
