from typing import Set

from obj import DcrGraph, RelationInfo, ExecutionInfo
from semantics_interface import SemanticsInterface

class SubprocessSemanticsMixin(SemanticsInterface):
    
    @classmethod
    def pending_children(cls, graph: DcrGraph, parent: str, included_pending: Set[str]=set()) -> bool:
        pending = False
        if not included_pending:
            included_pending = set(graph.marking.pending.keys()).intersection(graph.marking.effective_included)

        for child in graph.subprocesses[parent]:
            if child in graph.nestings:
                pending = pending or cls.pending_children(graph, child, included_pending)
            else:
                pending = pending or child in included_pending
        return pending
    
    @classmethod
    def is_enabled(cls, graph: DcrGraph, event: str) -> bool:
        if event in graph.subprocesses and cls.pending_children(graph, event):
            return False
        return super().is_enabled(graph, event)
    
    @classmethod
    def enabled(cls, graph: DcrGraph, res: Set[str]) -> Set[str]:
        for e in res.intersection(graph.subprocesses.keys()):
            if cls.pending_children(graph, e):
                res.discard(e)
        return super().enabled(graph, res)

    @classmethod
    def get_sources(cls, graph: DcrGraph, source: str, extended_sources: Set[str]) -> Set[str]:
        return super().get_sources(graph, source, extended_sources)
    
    @classmethod
    def get_targets(cls, graph: DcrGraph, target: str, extended_targets: Set[str]) -> Set[str]:
        return super().get_targets(graph, target, extended_targets)
    
    @classmethod
    def get_effect_order(cls, edges: list[tuple[str, str]]) -> list[str]:
        return super().get_effect_order(edges)
    
    @classmethod
    def is_valid(cls, graph: DcrGraph, source: str, target: str, relation_info: RelationInfo) -> bool:
        return super().is_valid(graph, source, target, relation_info)
    
    @classmethod
    def apply_effects(cls, graph: DcrGraph, original_source: str, effect_order: list[str]) -> DcrGraph:
        return super().apply_effects(graph, original_source, effect_order)
    
    @classmethod
    def update_executed_event_state(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        return super().update_executed_event_state(graph, event, execution_info)
    
    @classmethod
    def update_graph_state(cls, graph: DcrGraph, execution_info: ExecutionInfo) -> DcrGraph:
        return super().update_graph_state(graph, execution_info)

    # Assumes that no other extension will ever add an action after execution. If this changes, order may become an issue
    @classmethod
    def perform_execute(cls, graph: DcrGraph, event, execution_info: ExecutionInfo) -> DcrGraph:
        print(f'Subprocesses executing {event}')
        if event in graph.subprocesses_map and cls.is_enabled(graph, graph.subprocesses_map[event]):
            graph = cls.perform_execute(graph, graph.subprocesses_map[event], execution_info)
        return super().execute(graph, event, execution_info)
    
    @classmethod
    def check_execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> bool:
        return super().check_execute(graph, event, execution_info)
    
    @classmethod
    def execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        return super().execute(graph, event, execution_info)
    
    @classmethod
    def is_accepting(cls, graph: DcrGraph, res: Set[str]) -> bool:
        return super().is_accepting(graph, res)