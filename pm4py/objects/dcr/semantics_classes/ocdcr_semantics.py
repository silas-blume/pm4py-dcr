from typing import Set

from obj import DcrGraph, RelationInfo, ExecutionInfo
from semantics_interface import SemanticsInterface

class OcDcrSemanticsMixin(SemanticsInterface):
    
    @classmethod
    def is_enabled(cls, graph: DcrGraph, event: str) -> bool:
        return super().is_enabled(graph, event)
    
    @classmethod
    def enabled(cls, graph: DcrGraph, res: Set[str]) -> Set[str]:
        return super().enabled(graph, res)
    
    @classmethod
    def get_sources(cls, graph: DcrGraph, source: str, extended_sources: Set[str]) -> Set[str]:
        return super().get_sources(graph, source, extended_sources)
    
    @classmethod
    def get_targets(cls, graph: DcrGraph, target: str, extended_targets: Set[str]) -> Set[str]:
        return super().get_targets(graph, target, extended_targets)
    
    @classmethod
    def get_effect_order(cls, edges: list[tuple[str, str]]) -> list[str]:
        edges += [('spawn', 'exclude')]
        return super().get_effect_order(edges)
    
    @classmethod
    def is_valid(cls, graph: DcrGraph, source: str, target: str, relation_info: RelationInfo) -> bool:
        return super().is_valid(graph, source, target, relation_info)
    
    @classmethod
    def apply_effects(cls, graph: DcrGraph, original_source: str, effect_order: list[str]) -> DcrGraph:
        if effect_order[0] == 'spawn':
            for source in cls.get_sources(graph, original_source, set()):
                for original_target, relation_info in graph.spawns[original_source].items():
                    for target in cls.get_targets(graph, original_target, set()):
                        if cls.is_valid(graph, source, target, relation_info):
                            graph.spawn_subgraph(target, relation_info)
        return super().apply_effects(graph, original_source, effect_order)
    
    @classmethod
    def update_executed_event_state(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        return super().update_executed_event_state(graph, event, execution_info)
    
    @classmethod
    def update_graph_state(cls, graph: DcrGraph, execution_info: ExecutionInfo) -> DcrGraph:
        return super().update_graph_state(graph, execution_info)
    
    @classmethod
    def perform_execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        return super().perform_execute(graph, event, execution_info)
    
    @classmethod
    def check_execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> bool:
        return super().check_execute(graph, event, execution_info)
    
    @classmethod
    def execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        return super().execute(graph, event, execution_info)
    
    @classmethod
    def is_accepting(cls, graph: DcrGraph, res: Set[str]) -> bool:
        return super().is_accepting(graph, res)