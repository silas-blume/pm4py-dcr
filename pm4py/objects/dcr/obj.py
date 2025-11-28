"""
This module defines the components for modelling Declarative Process Models as
Dynamic Condition Response (DCR) Graphs.

Classes:
    Marking: Represents the state of events in terms of executed, included, and pending.
    DcrGraph: Encapsulates the structure and behavior of a DCR Graph, offering methods to query and manipulate it.

The classes are made to work with a modular implementation of the semantics classes. Therefore, they should always
be updated with any new information from new semantics mixins added to the create_semantics_class method in
semantics.py.
To allow the classes to hold all information for all current and future versions of the semantics with no
ambiguity about the structure of said information, typed dicts are used to store data for everything. As such,
Marking.__executed is typed Dict[str, ExecutedInfo] with the key being the name of the executed event and
ExecutedInfo being a typed dict, which currently only has the field 'last_execution_time'. Similarly for
Marking.__included we have IncludedInfo, which so far has no fields. This way any future extensions, which add
more info to either, knows exactly where to store and access it. These typed dicts are defined with total=False to
allow graphs to only contain the information required by its specific choice of semantics.
While the semantics classes handle changes to the graph through executions, any method that requires full knowledge
of all semantics to work must reside in the DcrGraph or Marking classes. Currently the only example is the
spawn_subgraph method which, in order to spawn a full DCR graph, must know of all the relevant fields in the
current implementation of the class.

The `dcr_template` dictionary provides a blueprint for initializing new DCR Graphs with default settings. It should
be kept in sync with the attributes of the DcrGraph and Marking classes.
"""
from copy import deepcopy
from typing import Set, Dict, List, Tuple, TypedDict, Any
from datetime import timedelta, datetime


dcr_template = {
    'events': set(),
    'marking': {'executed': {},
                'included': {},
                'pending': {},
                'data': {}
                },
    'currentTime': datetime.fromtimestamp(0),
    'labels': set(),
    'eventMap': {},
    'conditionedBy': {},
    'milestonedBy': {},
    'responsesTo': {},
    'noresponsesTo': {},
    'includesTo': {},
    'excludesTo': {},
    'setsValueTo': {},
    'spawnsTo': {},
    'nestedgroups': {},
    'nestedgroupsMap': {},
    'subprocesses': {},
    'subprocessesMap': {},
    'subgraphs': {},
}

class Marking:
    """
    This class contains the set of all markings.

    Attributes
    ----------
    self.__executed: Dict[str, ExecutedInfo]
        The set of executed events and the information pertaining to their execution
    self.__included: Dict[str, IncludedInfo]
        The set of included events and the information pertaining to their inclusion
    self.__effective_included: Set[str]
        The set of effectively included events
    self.__pending: Dict[str, PendingInfo]
        The set of pending events and the information pertaining to their ... pendyness
    self.__data: Dict[str, DataInfo]
        The set of events with data and the information pertaining to that data
    """
    def __init__(self, executed, included, pending, data=None) -> None:
        self.__executed = executed
        self.__included = included
        self.__effectiveIncluded = set()
        self.__pending = pending
        self.__data = {} if data is None else data

    class ExecutedInfo(TypedDict, total=False):
        last_execution_time: datetime

    @property
    def executed(self) -> Dict[str, ExecutedInfo]:
        return self.__executed

    @executed.setter
    def executed(self, value: Dict[str, ExecutedInfo]):
        self.__executed = value

    class IncludedInfo(TypedDict, total=False):
        pass

    @property
    def included(self) -> Dict[str, IncludedInfo]:
        return self.__included

    @included.setter
    def included(self, value: Dict[str, IncludedInfo]):
        self.__included = value

    @property
    def effective_included(self) -> set[str]:
        return self.__effectiveIncluded
    
    @effective_included.setter
    def effective_included(self, value: set[str]):
        self.__effectiveIncluded = value

    class PendingInfo(TypedDict, total=False):
        deadline: datetime

    @property
    def pending(self) -> Dict[str, PendingInfo]:
        return self.__pending

    @pending.setter
    def pending(self, value: Dict[str, PendingInfo]):
        self.__pending = value

    class DataInfo(TypedDict, total=False):
        data: Any
        expression: str | None
        input: bool

    @property
    def data(self) -> Dict[str, DataInfo]:
        return self.__data
    
    @data.setter
    def data(self, value: Dict[str, DataInfo]):
        self.__data = value

    # built-in functions for printing a visual string representation
    def __repr__(self) -> str:
        string = ""
        for key, value in vars(self).items():
            string += str(key.split("_")[-1])+": "+str(value)+"\n"
        return string

    def __str__(self) -> str:
        return self.__repr__()

    def __eq__(self, other) -> bool:
        return self.__repr__ == other.__repr__

    def __lt__(self, other) -> bool:
        return self.__repr__ < other.__repr__

    def __getitem__(self, item):
        for key, value in vars(self).items():
            if item == key.split("_")[-1]:
                return value

    def __setitem__(self, item, value):
        for key, _ in vars(self).items():
            if item == key.split("_")[-1]:
                setattr(self, key, value)


class RelationInfo(TypedDict, total=False):
    """
    Generic typeddict to act as base for the typedicts for each relation type.
    """
    guard: str
    for_all_sources: bool
    for_all_targets: bool

class ExecutionInfo(TypedDict, total=False):
    """
    Typeddict to handle varying input for executions depending on employed extensions.
    """
    time: datetime
    input: str

class ReturnInfo(TypedDict, total=False):
    """
    Typeddict to handle varying input for the return value of an execution depending on employed extensions.
    """
    enabled: Set[str]
    pending: Set[str]
    next_deadline: datetime

class DcrGraph(object):
    """
    The DCR Structure was implemented according to definition 3 in [1]_.
    Follows the idea of DCR graph as a set of tuples
    G = (E,Act,M,->*,*->,->{+,-},l)
    G graphs consist of a tuple of the events the activities,
    the marking of executed, included and pending events, all the relations, and the mapping of events to activities.

    References
    ----------
    .. [1] Thomas T. Hildebrandt and Raghava Rao Mukkamala, "Declarative Event-BasedWorkflow as Distributed Dynamic Condition Response Graphs",
      Electronic Proceedings in Theoretical Computer Science — 2011, Volume 69, 59–73. `DOI <10.4204/EPTCS.69.5>`_.

    Attributes
    ----------
    self.__events: Set[str]
        The set of all events in graph
    self.__marking: Marking
        the marking of the DCR graph loaded in
    self.__labels: Set[str]
        The set of activities in Graphs
    self.__labelMapping: Dict[str, Set[str]]:
        The set of event and their corresponding activity
    self.__condiditionsFor: Dict[str, Set[str]]:
        attribute containing all the conditions relation between events
    self.__responseTo: Dict[str, Set[str]]:
        attribute containing all the response relation between events
    self.__includesTo: Dict[str, Set[str]]:
        attribute containing all the include relations between events
    self.__excludesTo: Dict[str, Set[str]]:
        attribute containing all the exclude relations between events

    Methods
    --------
    getEvent(activity) -> str:
        returns the event of the associated activity
    getActivity(event) -> str:
        returns the activity of the given event
    getConstraints() -> int:
        returns the size of the model based on number of constraints

    Parameters
    ----------
    template : dict, optional
        A template dictionary to initialize the distributed and assignments from, if provided.

    Examples
    --------
    call this module and call the following
    graph = DCR_graph(dcr_template)

    Notes
    -------
    * DCR graph can not be initialized with a partially created template, use DCR_template for easy instantiation
    """

    def __init__(self, template=None, timing_dict: Dict[Tuple[str, str, str], timedelta] | None=None):
        self.__events = set() if template is None else template['events']
        self.__marking = Marking({}, {}, {}, {}) if template is None else (
            Marking(
                template['marking']['executed'],
                template['marking']['included'],
                template['marking']['pending'],
                template['marking'].get('data', {})
            ))
        self.__current_time = datetime.fromtimestamp(0) if template is None else template['currentTime']
        self.__returns = []
        self.__labels = set() if template is None else template['labels']
        self.__eventMap = {} if template is None else template['eventMap']
        self.__conditionedBy = {} if template is None else template['conditionedBy']
        self.__milestonedBy = {} if template is None else template['milestonedBy']
        self.__responsesTo = {} if template is None else template['responsesTo']
        self.__noresponsesTo = {} if template is None else template['noresponsesTo']
        self.__includesTo = {} if template is None else template['includesTo']
        self.__excludesTo = {} if template is None else template['excludesTo']
        self.__setsValueTo = {} if template is None else template['setsValueTo']
        self.__spawnsTo = {} if template is None else template['spawnsTo']
        self.__nestedgroups = {} if template is None else template['nestedgroups']
        self.__nestedgroupsMap = {} if template is None else template['nestedgroupsMap']
        self.__subprocesses = {} if template is None else template['subprocesses']
        self.__subprocessesMap = {} if template is None else template['subprocessesMap']
        self.__subgraphs = {} if template is None else self.subgraphs_from_template(template['subgraphs'])
        
        if len(self.__nestedgroupsMap) == 0 and len(self.__nestedgroups) > 0:
            self.__nestedgroupsMap = {}
            for group, events in self.__nestedgroups.items():
                for e in events:
                    if e not in self.__nestedgroupsMap:
                        self.__nestedgroupsMap[e] = set()
                    self.__nestedgroupsMap[e].add(group)
        if len(self.__subprocessesMap) == 0 and len(self.__subprocesses) > 0:
            self.__subprocessesMap = {}
            for group, events in self.__subprocesses.items():
                for e in events:
                    self.__subprocessesMap[e] = group
        if len(self.__subprocesses) > 0:
            self.set_effective_included()
        if timing_dict is not None:
            self.timed_dict_to_graph(timing_dict)
        if len(self.__subgraphs) > 0:
            self.initialise_spawn_containers(self, '')

    def set_effective_included(self) -> None:
        effective_included = set(self.__marking.included.keys())
        changed = True
        excluded = set()

        while changed:
            changed = False
            for parent, children in self.__subprocesses.items():
                if parent in excluded:
                    continue

                if parent not in effective_included:
                    changed = True
                    excluded.add(parent)
                    effective_included.difference_update(children)
            
        self.__marking.effective_included = effective_included

    def timed_dict_to_graph(self, timing_dict: Dict[Tuple[str, str, str], timedelta]) -> None:
        for timing, value in timing_dict.items():
            if timing[0] == 'CONDITION':
                e1 = timing[2]
                e2 = timing[1]
                if e1 not in self.__conditionedBy:
                    self.__conditionedBy[e1] = {}
                self.__conditionedBy[e1][e2]['delay'] = value
            elif timing[0] == 'RESPONSE':
                e1 = timing[1]
                e2 = timing[2]
                if e1 not in self.__responsesTo:
                    self.__responsesTo[e1] = {}
                self.__responsesTo[e1][e2]['deadline'] = value

    # @property functions to extract values used for data manipulation and testing
    @property
    def current_time(self) -> datetime:
        return self.__current_time
    
    @current_time.setter
    def current_time(self, value: datetime):
        self.__current_time = value

    @property
    def returns(self) -> List[ReturnInfo]:
        return self.__returns
    
    @returns.setter
    def returns(self, value: List[ReturnInfo]):
        self.__returns = value

    @property
    def events(self) -> Set[str]:
        return self.__events

    @events.setter
    def events(self, value: Set[str]):
        self.__events = value

    @property
    def marking(self) -> Marking:
        return self.__marking

    @marking.setter
    def marking(self, value: Marking) -> None:
        self.__marking = value

    @property
    def labels(self) -> Set[str]:
        return self.__labels

    @labels.setter
    def labels(self, value: Set[str]):
        self.__labels = value

    @property
    # def event_map(self) -> Dict[str, Set[str]]:
    def event_map(self) -> Dict[str, str]:
        return self.__eventMap

    @event_map.setter
    # def event_map(self, value: Dict[str, Set[str]]):
    def event_map(self, value: Dict[str, str]):
        self.__eventMap = value

    class ConditionInfo(RelationInfo):
        delay: timedelta

    @property
    def conditioned(self) -> Dict[str, Dict[str, ConditionInfo]]:
        return self.__conditionedBy

    @conditioned.setter
    def conditioned(self, value: Dict[str, Dict[str, ConditionInfo]]):
        self.__conditionedBy = value

    class MilestoneInfo(RelationInfo):
        pass

    @property
    def milestoned(self) -> Dict[str, Dict[str, MilestoneInfo]]:
        return self.__milestonedBy

    @milestoned.setter
    def milestoned(self, value: Dict[str, Dict[str, MilestoneInfo]]):
        self.__milestonedBy = value

    class ResponseInfo(RelationInfo):
        deadline: timedelta

    @property
    def responses(self) -> Dict[str, Dict[str, ResponseInfo]]:
        return self.__responsesTo

    @responses.setter
    def responses(self, value: Dict[str, Dict[str, ResponseInfo]]):
        self.__responsesTo = value

    class NoresponseInfo(RelationInfo):
        pass

    @property
    def noresponses(self) -> Dict[str, Dict[str, NoresponseInfo]]:
        return self.__noresponsesTo
    
    @noresponses.setter
    def noresponses(self, value: Dict[str, Dict[str, NoresponseInfo]]):
        self.__noresponsesTo = value

    class IncludeInfo(RelationInfo):
        pass

    @property
    def includes(self) -> Dict[str, Dict[str, IncludeInfo]]:
        return self.__includesTo

    @includes.setter
    def includes(self, value: Dict[str, Dict[str, IncludeInfo]]):
        self.__includesTo = value

    class ExcludeInfo(RelationInfo):
        pass

    @property
    def excludes(self) -> Dict[str, Dict[str, ExcludeInfo]]:
        return self.__excludesTo

    @excludes.setter
    def excludes(self, value: Dict[str, Dict[str, ExcludeInfo]]):
        self.__excludesTo = value

    class SetValueInfo(RelationInfo):
        expression: str

    @property
    def sets_value(self) -> Dict[str, Dict[str, SetValueInfo]]:
        return self.__setsValueTo
    
    @sets_value.setter
    def sets_value(self, value: Dict[str, Dict[str, SetValueInfo]]):
        self.__setsValueTo = value

    class SpawnInfo(RelationInfo):
        pass

    @property
    def spawns(self) -> Dict[str, Dict[str, SpawnInfo]]:
        return self.__spawnsTo
    
    @spawns.setter
    def spawns(self, value: Dict[str, Dict[str, SpawnInfo]]):
        self.__spawnsTo = value

    @property
    def nestings(self) -> Dict[str, Set[str]]:
        return self.__nestedgroups
    
    @nestings.setter
    def nestings(self, value: Dict[str, Set[str]]):
        self.__nestedgroups = value

    @property
    def nestings_map(self) -> Dict[str, Set[str]]:
        return self.__nestedgroupsMap

    @nestings_map.setter
    def nestings_map(self, value: Dict[str, Set[str]]):
        self.__nestedgroupsMap = value

    @property
    def subprocesses(self) -> Dict[str, Set[str]]:
        return self.__subprocesses

    @subprocesses.setter
    def subprocesses(self, value: Dict[str, Set[str]]):
        self.__subprocesses = value

    @property
    def subprocesses_map(self) -> Dict[str, str]:
        return self.__subprocessesMap

    @subprocesses_map.setter
    def subprocesses_map(self, value: Dict[str, str]):
        self.__subprocessesMap = value

    class SubgraphInfo(TypedDict):
        graph: 'DcrGraph'
        spawned: int

    @property
    def subgraphs(self) -> Dict[str, SubgraphInfo]:
        return self.__subgraphs
    
    @subgraphs.setter
    def subgraphs(self, value: Dict[str, SubgraphInfo]):
        self.__subgraphs = value

    def obj_to_template(self) -> Dict:
        res = deepcopy(dcr_template)
        res['events'] = self.__events
        res['marking']['executed'] = self.__marking.executed
        res['marking']['included'] = self.__marking.included
        res['marking']['pending'] = self.__marking.pending
        res['marking']['data'] = self.__marking.data
        res['labels'] = self.__labels
        res['eventMap'] = self.__eventMap
        res['conditionedBy'] = self.__conditionedBy
        res['milestonedBy'] = self.__milestonedBy
        res['responsesTo'] = self.__responsesTo
        res['noresponsesTo'] = self.__noresponsesTo
        res['includesTo'] = self.__includesTo
        res['excludesTo'] = self.__excludesTo
        res['setsValueTo'] = self.__setsValueTo
        res['spawnsTo'] = self.__spawnsTo
        res['nestedgroups'] = self.__nestedgroups
        res['nestedgroupsMap'] = self.__nestedgroupsMap
        res['subprocesses'] = self.__subprocesses
        res['subprocessesMap'] = self.__subprocessesMap
        res['subgraphs'] = self.subgraphs_to_template()

        return res
    
    def subgraphs_to_template(self) -> Dict:
        template = {}
        for graph_name, graph_info in self.__subgraphs.items():
            template[graph_name] = {
                'graph': graph_info['graph'].obj_to_template(),
                'spawned': graph_info['spawned']
            }
        return template
    
    def subgraphs_from_template(self, template_subgraphs: Dict) -> Dict[str, SubgraphInfo]:
        subgraphs = {}
        for key in template_subgraphs:
            if type(key) is not str:
                raise TypeError(f'Graph has subgraph with name {key} of type {type(key)}')
            info = template_subgraphs[key]
            if not isinstance(info, Dict):
                raise TypeError(f'Graph has subgraph {key} with info of type {type(info)}. Info must be dict')
            template_graph = info.get('graph')
            if template_graph is None:
                raise ValueError(f'Graph has subgraph name {key} without subgraph')
            graph = DcrGraph(template_graph)
            spawned = info.get('spawned')
            if spawned is None:
                spawned = 0
            subgraphs[key] = {'graph': graph, 'spawned': spawned}

        return subgraphs


    def initialise_spawn_containers(self, top_level_graph: 'DcrGraph', parent_string: str):
        for graph_name, info in self.__subgraphs.items():
            graph = info.get('graph')
            if graph is not None:
                graph_string = f"{parent_string}{graph_name}_"
                elements = graph.events | graph.nestings.keys() | graph.subprocesses.keys() | graph.subgraphs.keys()
                top_level_graph.nestings.update({graph_string + element: set() for element in elements})
                if len(graph.subgraphs) > 0:
                    graph.initialise_spawn_containers(top_level_graph, graph_string)


    def spawn_subgraph(self, subgraph_name: str, relation_info: SpawnInfo):
        subgraph = self.__subgraphs[subgraph_name]['graph']
        if subgraph is None:
            return
        spawn_number = self.__subgraphs[subgraph_name]['spawned'] + 1

        def container_name(name: str) -> str:
            return f"{subgraph_name}_{name}"

        def spawn_name(name: str) -> str:
            return f"{subgraph_name}_{name}_{spawn_number}"

        self.__nestedgroups.update({spawn_name(nesting): {spawn_name(event) for event in subgraph.nestings[nesting]} for nesting in subgraph.nestings})
        self.__nestedgroupsMap.update({spawn_name(event): {spawn_name(nesting) for nesting in subgraph.nestings_map[event]} for event in subgraph.nestings_map})
        self.__subprocesses.update({spawn_name(subprocess): {spawn_name(event) for event in subgraph.subprocesses[subprocess]} for subprocess in subgraph.subprocesses})
        self.__subprocessesMap.update({spawn_name(event): spawn_name(subgraph.subprocesses_map[event]) for event in subgraph.subprocesses_map})
        self.__subgraphs.update({spawn_name(subsubgraph): info for subsubgraph, info in subgraph.subgraphs.items()})
        for event in subgraph.events:
            container = container_name(event)
            event_name = spawn_name(event)
            self.events.add(event_name)
            self.nestings[container].add(event_name)
            if event_name not in self.nestings_map:
                self.nestings_map[event_name] = set()
            self.nestings_map[event_name].add(container)

        in_nest = subgraph_name in self.__nestedgroupsMap
        in_sub = subgraph_name in self.__subprocessesMap
        if in_nest or in_sub:
            elements = subgraph.events | subgraph.nestings.keys() | subgraph.subprocesses.keys() | subgraph.subgraphs.keys()
            top_level_elements = {spawn_name(e) for e in elements if e not in subgraph.nestings_map and e not in subgraph.subprocesses_map}
            if in_nest:
                for n in self.__nestedgroupsMap[subgraph_name]:
                    self.__nestedgroups[n].update(top_level_elements)
                for e in top_level_elements:
                    self.__nestedgroupsMap[e].update(self.__nestedgroupsMap[subgraph_name])
            if in_sub:
                for s in self.__subprocessesMap[subgraph_name]:
                    self.__subprocesses[s].update(top_level_elements)
                for e in top_level_elements:
                    self.__subprocessesMap[e] = self.__subprocessesMap[subgraph_name]

        for target, source_dict in subgraph.conditioned.items():
            for source, info in source_dict.items():
                effective_target = container_name(target) if info.get('for_all_targets', False) else spawn_name(target)
                effective_source = container_name(source) if info.get('for_all_sources', False) else spawn_name(source)
                self.__conditionedBy[effective_target][effective_source] = info

        for target, source_dict in subgraph.milestoned.items():
            for source, info in source_dict.items():
                effective_target = container_name(target) if info.get('for_all_targets', False) else spawn_name(target)
                effective_source = container_name(source) if info.get('for_all_sources', False) else spawn_name(source)
                self.__milestonedBy[effective_target][effective_source] = info

        for source, target_dict in subgraph.responses.items():
            for target, info in target_dict.items():
                effective_source = container_name(source) if info.get('for_all_sources', False) else spawn_name(source)
                effective_target = container_name(target) if info.get('for_all_targets', False) else spawn_name(target)
                self.__responsesTo[effective_source][effective_target] = info

        for source, target_dict in subgraph.noresponses.items():
            for target, info in target_dict.items():
                effective_source = container_name(source) if info.get('for_all_sources', False) else spawn_name(source)
                effective_target = container_name(target) if info.get('for_all_targets', False) else spawn_name(target)
                self.__noresponsesTo[effective_source][effective_target] = info

        for source, target_dict in subgraph.includes.items():
            for target, info in target_dict.items():
                effective_source = container_name(source) if info.get('for_all_sources', False) else spawn_name(source)
                effective_target = container_name(target) if info.get('for_all_targets', False) else spawn_name(target)
                self.__includesTo[effective_source][effective_target] = info

        for source, target_dict in subgraph.excludes.items():
            for target, info in target_dict.items():
                effective_source = container_name(source) if info.get('for_all_sources', False) else spawn_name(source)
                effective_target = container_name(target) if info.get('for_all_targets', False) else spawn_name(target)
                self.__excludesTo[effective_source][effective_target] = info

        for source, target_dict in subgraph.sets_value.items():
            for target, info in target_dict.items():
                effective_source = container_name(source) if info.get('for_all_sources', False) else spawn_name(source)
                effective_target = container_name(target) if info.get('for_all_targets', False) else spawn_name(target)
                self.__setsValueTo[effective_source][effective_target] = info

        for source, target_dict in subgraph.spawns.items():
            for target, info in target_dict.items():
                effective_source = container_name(source) if info.get('for_all_sources', False) else spawn_name(source)
                effective_target = container_name(target) if info.get('for_all_targets', False) else spawn_name(target)
                self.__spawnsTo[effective_source][effective_target] = info

        self.subgraphs[subgraph_name]['spawned'] = spawn_number
        

    def get_event(self, label: str) -> str | None:
        """
        Get the event ID corresponding to the label.

        Parameters
        ----------
        label
            the label of an event

        Returns
        -------
        event
            the event ID for the label
        """
        return self.event_map.get(label)

    def get_label(self, event: str) -> str | None:
        """
        get the label of an Event

        Parameters
        ----------
        event
            event ID

        Returns
        -------
            the label of the event
        """
        for label, label_event in self.event_map.items():
            if event == label_event:
                return label

    def get_constraints(self) -> int:
        """
        compute constraints in DCR Graph
            - conditions
            - milestones
            - responses
            - no_responses
            - includes
            - excludes
            - set_values
            - spawns

        Returns
        -------
        no
            number of constraints
        """
        no = 0
        for i in self.__conditionedBy.values():
            no += len(i)
        for i in self.__milestonedBy.values():
            no += len(i)
        for i in self.__responsesTo.values():
            no += len(i)
        for i in self.__noresponsesTo.values():
            no += len(i)
        for i in self.__excludesTo.values():
            no += len(i)
        for i in self.__includesTo.values():
            no += len(i)
        for i in self.__setsValueTo.values():
            no += len(i)
        for i in self.__spawnsTo.values():
            no += len(i)
        return no

    def __repr__(self):
        string = ""
        for key, value in vars(self).items():
            string += str(key.split("_")[-1])+": "+str(value)+"\n"
        return string

    def __str__(self):
        return self.__repr__()

    def __eq__(self, other):
        return self.__repr__ == other.__repr__

    def __lt__(self, other):
        return self.__repr__ < other.__repr__

    def __getitem__(self, item):
        for key, value in vars(self).items():
            if item == key.split("_")[-1]:
                return value
        return set()

    def __setitem__(self, item, value):
        for key,_ in vars(self).items():
            if item == key.split("_")[-1]:
                setattr(self, key, value)

