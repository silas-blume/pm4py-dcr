from typing import Set

from obj import DcrGraph, RelationInfo, ExecutionInfo
from semantics_interface import SemanticsInterface

class BaseSemantics(SemanticsInterface):

    # TODO: Add calls to is_valid
    @classmethod
    def is_enabled(cls, graph: DcrGraph, event: str) -> bool:
        if not event in graph.marking.effective_included:
            return False
        if event in graph.conditioned and len(
            set(graph.conditioned[event].keys()).intersection(graph.marking.effective_included.difference(graph.marking.executed.keys()))
        ) > 0:
            return False
        if event in graph.milestoned and len(
            set(graph.milestoned[event].keys()).intersection(graph.marking.effective_included.intersection(graph.marking.pending.keys()))
        ) > 0:
            return False
        return super().is_enabled(graph, event)
    
    @classmethod
    def enabled(cls, graph: DcrGraph, res: Set[str] | None = None) -> Set[str]:
        res = graph.marking.effective_included.copy()
        for e in res.intersection(graph.conditioned.keys()):
            if len(graph.marking.effective_included.intersection(graph.conditioned[e].keys()).difference(graph.marking.executed.keys())) > 0:
                res.discard(e)
        for e in res.intersection(graph.milestoned.keys()):
            if len(graph.marking.effective_included.intersection(graph.milestoned[e].keys()).intersection(graph.marking.pending.keys())) > 0:
                res.discard(e)
        return super().enabled(graph, res)
    
    @classmethod
    def get_sources(cls, graph: DcrGraph, source: str, extended_sources: Set[str]  | None = None) -> Set[str]:
        extended_sources = set()
        extended_sources.add(source)
        length = 1

        while True:
            for source in extended_sources:
                if source in graph.nestings_map:
                    extended_sources.update(graph.nestings_map[source])
            if len(extended_sources) == length:
                break
            length = len(extended_sources)
            
        return super().get_sources(graph, source, extended_sources)
    
    @classmethod
    def get_targets(cls, graph: DcrGraph, target: str, extended_targets: Set[str]  | None = None) -> Set[str]:
        extended_targets = set()
        extended_targets.add(target)
        length = 1

        while True:
            for target in extended_targets:
                if target in graph.nestings:
                    extended_targets.update(graph.nestings[target])
            if len(extended_targets) == length:
                break
            length = len(extended_targets)
            
        return super().get_targets(graph, target, extended_targets)
    
    @classmethod
    def get_effect_order(cls, edges=[]) -> list[str]:
        edges = [('exclude', 'include'), ('include', 'noresponse'), ('noresponse', 'response')]
        return super().get_effect_order(edges)
    
    @classmethod
    def is_valid(cls, graph: DcrGraph, source: str, target: str, relation_info: RelationInfo) -> bool:
        return super().is_valid(graph, source, target, relation_info)
    
    @classmethod
    def apply_effects(cls, graph: DcrGraph, original_source: str, effect_order: list[str]) -> DcrGraph:
        effect_type = effect_order[0]
        if effect_type in ['exclude', 'include', 'noresponse', 'response']:
            sources = cls.get_sources(graph, original_source)

            match effect_type:
                case 'exclude':
                    if original_source in graph.excludes:
                        for original_target, relation_info in graph.excludes[original_source].items():
                            for target in cls.get_targets(graph, original_target):
                                for source in sources:
                                    if cls.is_valid(graph, source, target, relation_info):
                                        del graph.marking.included[target]
                    graph.set_effective_included()

                case 'include':
                    if original_source in graph.includes:
                        for original_target, relation_info in graph.includes[original_source].items():
                            for target in cls.get_targets(graph, original_target):
                                for source in sources:
                                    if cls.is_valid(graph, source, target, relation_info):
                                        graph.marking.included[target] = {}
                    graph.set_effective_included()

                case 'noresponse':
                    if original_source in graph.noresponses:
                        for original_target, relation_info in graph.noresponses[original_source].items():
                            for target in cls.get_targets(graph, original_target):
                                for source in sources:
                                    if cls.is_valid(graph, source, target, relation_info):
                                        del graph.marking.pending[target]

                case 'response':
                    if original_source in graph.responses:
                        for original_target, relation_info in graph.responses[original_source].items():
                            for target in cls.get_targets(graph, original_target):
                                for source in sources:
                                    if cls.is_valid(graph, source, target, relation_info):
                                        graph.marking.pending[target] = {}
            
        return super().apply_effects(graph, original_source, effect_order)
    
    @classmethod
    def update_executed_event_state(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        if event in graph.marking.pending:
            del graph.marking.pending[event]
        graph.marking.executed[event] = {}
        return super().update_executed_event_state(graph, event, execution_info)
    
    @classmethod
    def update_graph_state(cls, graph: DcrGraph, execution_info: ExecutionInfo) -> DcrGraph:
        return super().update_graph_state(graph, execution_info)

    @classmethod
    def perform_execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        print(f'Base executing {event}')

        graph = cls.update_graph_state(graph, execution_info)
        
        graph = cls.update_executed_event_state(graph, event, execution_info)

        effect_order = cls.get_effect_order()

        graph = cls.apply_effects(graph, event, effect_order)

        return super().perform_execute(graph, event, execution_info)
    
    @classmethod
    def check_execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> bool:
        if event not in graph.events:
            eventName = graph.get_event(event)
            if eventName is None:
                raise ValueError(f"{event} is not in graph")
            event = eventName
        if not cls.is_enabled(graph, event):
            raise ValueError(f"{event} is not enabled")
        return super().check_execute(graph, event, execution_info)
    
    @classmethod
    def execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        cls.check_execute(graph, event, execution_info)
        graph.returns.append({})
        graph = cls.perform_execute(graph, event, execution_info)
        return super().execute(graph, event, execution_info)

    @classmethod
    def is_accepting(cls, graph: DcrGraph, res: Set[str] | None = None) -> bool:
        res = set(graph.marking.pending.keys()).intersection(graph.marking.effective_included)
        return super().is_accepting(graph, res)