"""
Decorator that adds data-guard conformance checking to the checker chain.

Wraps any ``Checker`` instance and adds data-aware violation detection for
guarded condition, milestone, and exclude relations.
"""
from pm4py.algo.conformance.dcr.decorators.decorator import Decorator
from pm4py.algo.conformance.dcr.rules.data_guard import CheckDataGuard
from pm4py.objects.dcr.data.obj import DataDcrGraph
from pm4py.objects.dcr.obj import DcrGraph
from typing import Any, Dict, List, Optional, Tuple, Union


class DataConstraintDecorator(Decorator):
    """
    Decorates a Checker to add data guard violation checks.

    * ``enabled_checker`` — additionally checks guarded conditions and
      milestones for violations.
    * ``all_checker`` — stores input values from event attributes into the
      graph marking so that guard evaluation during execution has access
      to real data from the event log.
    * ``accepting_checker`` — delegates to the underlying checker.
    """

    def enabled_checker(self, event: str, graph: Union[DataDcrGraph, DcrGraph],
                        deviations: List[Tuple[str, Any]],
                        parameters: Optional[Dict[Union[str, Any], Any]] = None) -> None:
        # Let the base checker run first (conditions, excludes, includes)
        self._checker.enabled_checker(event, graph, deviations, parameters=parameters)
        # Then check data guards
        if isinstance(graph, DataDcrGraph):
            CheckDataGuard.check_enabled_rule(event, graph, deviations)
            if parameters and 'executionHistory' in parameters:
                CheckDataGuard.check_exclude_rule(
                    event, graph, parameters['executionHistory'], deviations
                )

    def all_checker(self, event: str, event_attributes: dict,
                    graph: Union[DataDcrGraph, DcrGraph],
                    deviations: List[Tuple[str, Any]],
                    parameters: Optional[Dict[Union[str, Any], Any]] = None) -> None:
        # Let the base checker run first
        self._checker.all_checker(event, event_attributes, graph, deviations, parameters=parameters)

        # For data-aware graphs, extract input values from event attributes
        # and store them so they're available during guard evaluation.
        if isinstance(graph, DataDcrGraph) and parameters:
            data_attr_key = parameters.get('data_attribute_key', None)
            if data_attr_key and data_attr_key in event_attributes:
                # If a specific data attribute key is configured, use it
                graph.marking.event_values[event] = event_attributes[data_attr_key]

    def accepting_checker(self, graph: Union[DataDcrGraph, DcrGraph],
                          responses: List[Tuple[str, str]],
                          deviations: List[Tuple[str, Any]],
                          parameters: Optional[Dict[Union[str, Any], Any]] = None) -> None:
        self._checker.accepting_checker(graph, responses, deviations, parameters=parameters)
