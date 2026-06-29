"""
Data-aware DCR Graph model.

This module extends the TimedDcrGraph with support for data types, event values,
decision expressions, and guarded relations as formalised in Definition 2 of [1]_.

A data-aware DCR graph adds the following concepts on top of timed DCR graphs:

* **Event types** — each event has a type (Int, Bool, or Void).
* **Decision function** — each event is either an *input event* (receiving a
  value from the environment during execution) or a *decision event* (computing
  its value from an expression over the current marking).
* **Event values in the marking** — the marking records the most-recently
  computed or received value for each executed event.
* **Guards on relations** — every relation (condition, response, include,
  exclude, milestone, no-response) can carry a boolean guard expression.  The
  relation only takes effect when the guard evaluates to ``True`` in the current
  marking.

Classes
-------
DataMarking
    Extends TimedMarking with a dictionary of event values.
DataDcrGraph
    Extends TimedDcrGraph with event types, decisions, and guarded relations.

References
----------
.. [1] Hildebrandt, T.T., Normann, H., Marquard, M., Debois, S., Slaats, T.
   (2022). Decision Modelling in Timed Dynamic Condition Response Graphs with
   Data.  BPM 2021 Workshops, LNBIP 436, pp. 362-374.
"""
from copy import deepcopy
from typing import Any, Callable, Dict, Optional, Set

from pm4py.objects.dcr.data.expressions import (
    DataType, Expression, Guard, INPUT_MARKER,
)
from pm4py.objects.dcr.data.predicate_loader import DataPredicate
from pm4py.objects.dcr.timed.obj import TimedDcrGraph, TimedMarking

# Template keys for the six guarded relation types, paired with their
# corresponding private attribute names on DataDcrGraph.  Keeping this in
# one place avoids scattering the same six names across __init__,
# obj_to_template, get_constraints, and __eq__.
_GUARDED_RELATION_KEYS = (
    'guardedConditions',
    'guardedResponses',
    'guardedIncludes',
    'guardedExcludes',
    'guardedMilestones',
    'guardedNoResponses',
)


class DataMarking(TimedMarking):
    """
    Marking extended with event values (Definition 2, item iv).

    In addition to the standard marking components (executed, included, pending)
    and timed components (executed_time, pending_deadline), the data marking
    stores the most-recently produced value for each executed event.

    Attributes
    ----------
    event_values : Dict[str, Any]
        Mapping from event id to its current value.  An event has a value after
        it has been executed at least once.  The type of the value must match
        the event's declared type (``int``, ``bool``, or ``None`` for void).
    """

    def __init__(self, executed=None, included=None, pending=None,
                 executed_time=None, pending_deadline=None,
                 event_values=None):
        super().__init__(
            executed if executed is not None else set(),
            included if included is not None else set(),
            pending if pending is not None else set(),
            executed_time, pending_deadline,
        )
        self.__event_values: Dict[str, Any] = {} if event_values is None else event_values

    @property
    def event_values(self) -> Dict[str, Any]:
        return self.__event_values

    @event_values.setter
    def event_values(self, value: Dict[str, Any]):
        self.__event_values = value

    def reset(self, initial_marking) -> None:
        super().reset(initial_marking)
        self.__event_values = dict(initial_marking.get('eventValues', {}))

    def __repr__(self):
        base = super().__repr__()
        return base.rstrip('}') + f', event_values: {self.__event_values}}}'


class DataDcrGraph(TimedDcrGraph):
    """
    A DCR graph with data types, decisions, and guarded relations (Definition 2).

    Extends the full DCR hierarchy (DcrGraph → Distributed → Extended →
    Hierarchical → Timed → **Data**) with:

    * ``event_types`` — ``Dict[str, DataType]``: the type of each event.
    * ``decisions`` — ``Dict[str, Expression | '?']``: the decision function.
      Events mapped to ``'?'`` are *input events* (value provided at execution
      time from the environment / event log).  Events mapped to an
      ``Expression`` are *decision events* whose value is computed.
    * ``guarded_conditions`` — ``Dict[str, Dict[str, Guard]]``: target →
      {source → guard} for guarded condition relations.
    * ``guarded_responses`` — ``Dict[str, Dict[str, Guard]]``: source →
      {target → guard} for guarded response relations.
    * ``guarded_includes`` — ``Dict[str, Dict[str, Guard]]``: source →
      {target → guard} for guarded include relations.
    * ``guarded_excludes`` — ``Dict[str, Dict[str, Guard]]``: source →
      {target → guard} for guarded exclude relations.
    * ``guarded_milestones`` — ``Dict[str, Dict[str, Guard]]``: target →
      {source → guard} for guarded milestone relations.
    * ``guarded_noresponses`` — ``Dict[str, Dict[str, Guard]]``: source →
      {target → guard} for guarded no-response relations.

    Unguarded relations (from the parent classes) continue to work as before.
    Guarded relations are *additional* constraints that only take effect when
    their guard evaluates to true.

    Parameters
    ----------
    template : dict, optional
        Template dictionary.  Recognised additional keys:

        - ``'eventTypes'``: ``Dict[str, str]`` — event_id → type name
        - ``'decisions'``: ``Dict[str, Expression | '?']``
        - ``'guardedConditions'``: ``Dict[str, Dict[str, Guard]]``
        - ``'guardedResponses'``: ``Dict[str, Dict[str, Guard]]``
        - ``'guardedIncludes'``: ``Dict[str, Dict[str, Guard]]``
        - ``'guardedExcludes'``: ``Dict[str, Dict[str, Guard]]``
        - ``'guardedMilestones'``: ``Dict[str, Dict[str, Guard]]``
        - ``'guardedNoResponses'``: ``Dict[str, Dict[str, Guard]]``
        - ``'marking'`` may contain ``'eventValues': Dict[str, Any]``
    """

    def __init__(self, template=None):
        super().__init__(template)

        # --- Event types (Definition 2, ii) ---
        if template is not None and 'eventTypes' in template:
            raw = template['eventTypes']
            self.__event_types: Dict[str, DataType] = {
                e: (DataType(t) if isinstance(t, str) else t) for e, t in raw.items()
            }
        else:
            self.__event_types: Dict[str, DataType] = {}

        # --- Decision function (Definition 2, iii) ---
        self.__decisions: Dict[str, Any] = (
            {} if template is None else template.get('decisions', {})
        )

        # --- Data marking ---
        if template is not None:
            ev = template.get('marking', {}).get('eventValues', {})
            self.__marking = DataMarking(
                template['marking'].get('executed', set()),
                template['marking'].get('included', set()),
                template['marking'].get('pending', set()),
                template['marking'].get('executedTime', {}),
                template['marking'].get('pendingDeadline', {}),
                ev,
            )
        else:
            self.__marking = DataMarking()

        # --- Guarded relations (Definition 2, v-vii) ---
        self.__guarded_relations: Dict[str, Dict[str, Dict[str, Guard]]] = {}
        for key in _GUARDED_RELATION_KEYS:
            self.__guarded_relations[key] = (
                {} if template is None else template.get(key, {})
            )

        # --- Predicate registry (injectable user functions for guard evaluation) ---
        self.__predicate_registry: Dict[str, DataPredicate] = {}

    # ---- Marking override ----

    @property
    def marking(self):
        return self.__marking

    @marking.setter
    def marking(self, value):
        self.__marking = value

    # ---- Event types ----

    @property
    def event_types(self) -> Dict[str, DataType]:
        return self.__event_types

    @event_types.setter
    def event_types(self, value: Dict[str, DataType]):
        self.__event_types = value

    # ---- Decisions ----

    @property
    def decisions(self) -> Dict[str, Any]:
        return self.__decisions

    @decisions.setter
    def decisions(self, value: Dict[str, Any]):
        self.__decisions = value

    def is_input_event(self, event: str) -> bool:
        """Check if an event is an input event (D(e) = ?)."""
        return self.__decisions.get(event) == INPUT_MARKER

    def is_decision_event(self, event: str) -> bool:
        """Check if an event is a decision event (D(e) is an Expression)."""
        d = self.__decisions.get(event)
        return d is not None and d != INPUT_MARKER and isinstance(d, Expression)

    # ---- Predicate registry ----

    @property
    def predicate_registry(self) -> Dict[str, DataPredicate]:
        """Mapping from predicate name to callable for guard evaluation."""
        return self.__predicate_registry

    @predicate_registry.setter
    def predicate_registry(self, value: Dict[str, DataPredicate]):
        self.__predicate_registry = value

    # ---- Guarded relations ----

    def _get_guarded(self, key: str) -> Dict[str, Dict[str, Guard]]:
        return self.__guarded_relations[key]

    def _set_guarded(self, key: str, value: Dict[str, Dict[str, Guard]]):
        self.__guarded_relations[key] = value

    @property
    def guarded_conditions(self) -> Dict[str, Dict[str, Guard]]:
        return self._get_guarded('guardedConditions')

    @guarded_conditions.setter
    def guarded_conditions(self, value):
        self._set_guarded('guardedConditions', value)

    @property
    def guarded_responses(self) -> Dict[str, Dict[str, Guard]]:
        return self._get_guarded('guardedResponses')

    @guarded_responses.setter
    def guarded_responses(self, value):
        self._set_guarded('guardedResponses', value)

    @property
    def guarded_includes(self) -> Dict[str, Dict[str, Guard]]:
        return self._get_guarded('guardedIncludes')

    @guarded_includes.setter
    def guarded_includes(self, value):
        self._set_guarded('guardedIncludes', value)

    @property
    def guarded_excludes(self) -> Dict[str, Dict[str, Guard]]:
        return self._get_guarded('guardedExcludes')

    @guarded_excludes.setter
    def guarded_excludes(self, value):
        self._set_guarded('guardedExcludes', value)

    @property
    def guarded_milestones(self) -> Dict[str, Dict[str, Guard]]:
        return self._get_guarded('guardedMilestones')

    @guarded_milestones.setter
    def guarded_milestones(self, value):
        self._set_guarded('guardedMilestones', value)

    @property
    def guarded_noresponses(self) -> Dict[str, Dict[str, Guard]]:
        return self._get_guarded('guardedNoResponses')

    @guarded_noresponses.setter
    def guarded_noresponses(self, value):
        self._set_guarded('guardedNoResponses', value)

    # ---- Template conversion ----

    def obj_to_template(self):
        res = super().obj_to_template()
        res['eventTypes'] = {
            e: t.value for e, t in self.__event_types.items()
        }
        res['decisions'] = dict(self.__decisions)
        for key in _GUARDED_RELATION_KEYS:
            res[key] = deepcopy(self.__guarded_relations[key])
        res['marking']['eventValues'] = dict(self.__marking.event_values)
        return res

    # ---- Constraint counting ----

    def get_constraints(self) -> int:
        no = super().get_constraints()
        for key in _GUARDED_RELATION_KEYS:
            for targets in self.__guarded_relations[key].values():
                no += len(targets)
        return no

    def __eq__(self, other):
        if not isinstance(other, DataDcrGraph):
            return False
        if not super().__eq__(other):
            return False
        if self.event_types != other.event_types or self.decisions != other.decisions:
            return False
        return all(
            self._get_guarded(key) == other._get_guarded(key)
            for key in _GUARDED_RELATION_KEYS
        )
