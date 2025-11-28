from typing import Set, Tuple
from datetime import datetime

from obj import DcrGraph, RelationInfo, ExecutionInfo
from semantics_interface import SemanticsInterface

class TimeSemanticsMixin(SemanticsInterface):

    @classmethod
    def is_enabled(cls, graph: DcrGraph, event: str) -> bool:
        if event in graph.conditioned:
            for source, relation_info in graph.conditioned[event].items():
                execution_time = graph.marking.executed[source].get('last_execution_time')
                if (source in graph.marking.effective_included
                    and execution_time is not None
                    and execution_time + relation_info['delay'] > graph.current_time
                    and cls.is_valid(graph, source, event, relation_info)):
                    return False
        return super().is_enabled(graph, event)
    
    @classmethod
    def enabled(cls, graph: DcrGraph, res: Set[str]) -> Set[str]:
        for e in res.intersection(graph.conditioned.keys()):
            for source, relation_info in graph.conditioned[e].items():
                execution_time = graph.marking.executed[source].get('last_execution_time')
                if (source in graph.marking.effective_included
                    and execution_time is not None
                    and execution_time + relation_info['delay'] > graph.current_time
                    and cls.is_valid(graph, source, e, relation_info)):
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
        if effect_order[0] == 'response':
            for source in cls.get_sources(graph, original_source, set()):
                for original_target, relation_info in graph.responses[original_source].items():
                    for target in cls.get_targets(graph, original_target, set()):
                        if cls.is_valid(graph, source, target, relation_info):
                            graph.marking.pending[target]['deadline'] = graph.current_time + relation_info['deadline']
            
        return super().apply_effects(graph, original_source, effect_order)
    
    @classmethod
    def update_executed_event_state(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        event_time = execution_info.get('time')
        if event_time is not None:
            graph.marking.executed[event]['last_execution_time'] = event_time
        return super().update_executed_event_state(graph, event, execution_info)
    
    @classmethod
    def update_graph_state(cls, graph: DcrGraph, execution_info: ExecutionInfo) -> DcrGraph:
        execution_time = execution_info.get('time')
        if execution_time is None:
            raise ValueError(f"Execution has no execution time. If performing untimed executions, use semantics without the time extension.")
        if execution_time < graph.current_time:
            raise ValueError(f"Execution at time {execution_time} is prior to graph's current state of {graph.current_time}")
        graph.current_time =execution_time
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
    
    @staticmethod
    def next_deadline(graph: DcrGraph) -> Tuple[datetime | None, str | None]:
        next_deadline = None
        pending_event = None
        for event, pending_info in graph.marking.pending.items():
            deadline = pending_info.get('deadline')
            if deadline is not None and event in graph.marking.effective_included:
                if next_deadline is None or deadline < next_deadline:
                    next_deadline = deadline
                    pending_event = event
        return next_deadline, pending_event