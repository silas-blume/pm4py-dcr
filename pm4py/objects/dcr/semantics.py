from typing import Set
from collections import defaultdict, deque

from obj import DcrGraph, RelationInfo, ExecutionInfo
from semantics_interface import SemanticsInterface
from semantics_classes.base_semantics import BaseSemantics
from semantics_classes.subprocess_semantics import SubprocessSemanticsMixin
from semantics_classes.time_semantics import TimeSemanticsMixin
from semantics_classes.data_and_guard_semantics import DataAndGuardSemanticsMixin
from semantics_classes.ocdcr_semantics import OcDcrSemanticsMixin


class EmptySemantics(SemanticsInterface):

    @classmethod
    def is_enabled(cls, graph: DcrGraph, event: str) -> bool:
        return True

    @classmethod
    def enabled(cls, graph: DcrGraph, res: Set[str]) -> Set[str]:
        return res

    @classmethod
    def get_sources(cls, graph: DcrGraph, source: str, extended_sources: Set[str]) -> Set[str]:
        return extended_sources
    
    @classmethod
    def get_targets(cls, graph: DcrGraph, target: str, extended_targets: Set[str]) -> Set[str]:
        return extended_targets

    @classmethod
    def get_effect_order(cls, edges: list[tuple[str, str]]) -> list[str]:
        graph = defaultdict(set)
        in_degree = defaultdict(int)
        nodes = set()

        for before, after in edges:
            graph[before].add(after)
            in_degree[after] += 1
            nodes.add(before)
            nodes.add(after)

        # Nodes with zero incoming edges
        zero_in_degree = deque([n for n in nodes if in_degree[n] == 0])
        order = []

        while zero_in_degree:
            node = zero_in_degree.popleft()
            order.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    zero_in_degree.append(neighbor)

        if len(order) != len(nodes):
            raise ValueError("Cycle detected in effect ordering!")

        return order
    
    @classmethod
    def is_valid(cls, graph: DcrGraph, source: str, target: str, relation_info: RelationInfo) -> bool:
        return True
    
    @classmethod
    def apply_effects(cls, graph: DcrGraph, original_source: str, effect_order: list[str]) -> DcrGraph:
        if len(effect_order) < 2:
            return graph
        return cls.apply_effects(graph, original_source, effect_order[1:])
    
    @classmethod
    def update_executed_event_state(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        return graph
    
    @classmethod
    def update_graph_state(cls, graph: DcrGraph, execution_info: ExecutionInfo) -> DcrGraph:
        return graph
    
    @classmethod
    def perform_execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        return graph
    
    @classmethod
    def check_execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> bool:
        return True
    
    @classmethod
    def execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        graph.returns[-1]['enabled'] = cls.enabled(graph, set())
        graph.returns[-1]['pending'] = set(graph.marking.pending.keys())
        return graph
    
    @classmethod
    def is_accepting(cls, graph: DcrGraph, res: Set[str]) -> bool:
        return len(res) == 0


class DcrSemantics():

    @classmethod
    def create_semantics_class(cls, name, subprocesses=False, time=False, data_and_guards=False, object_centric=False):
        mixin_map = {
            'subprocesses': SubprocessSemanticsMixin,
            'time': TimeSemanticsMixin,
            'data_and_guards': DataAndGuardSemanticsMixin,
            'object_centric': OcDcrSemanticsMixin,
        }

        extensions = [mixin for flag, mixin in mixin_map.items() if locals()[flag]]

        bases = (BaseSemantics,) + tuple(extensions) + (EmptySemantics,)

        return type(name, bases, {})