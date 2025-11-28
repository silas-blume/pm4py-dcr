from abc import ABC, abstractmethod
from typing import Set

from obj import DcrGraph, RelationInfo, ExecutionInfo

class SemanticsInterface(ABC):

    @classmethod
    @abstractmethod
    def is_enabled(cls, graph: DcrGraph, event: str) -> bool:
        pass

    @classmethod
    @abstractmethod
    def enabled(cls, graph: DcrGraph, res: Set[str]) -> Set[str]:
        pass

    @classmethod
    @abstractmethod
    def get_sources(cls, graph: DcrGraph, source: str, extended_sources: Set[str]) -> Set[str]:
        pass
    
    @classmethod
    @abstractmethod
    def get_targets(cls, graph: DcrGraph, target: str, extended_targets: Set[str]) -> Set[str]:
        pass

    @classmethod
    @abstractmethod
    def get_effect_order(cls, edges: list[tuple[str, str]]) -> list[str]:
        pass

    @classmethod
    @abstractmethod
    def is_valid(cls, graph: DcrGraph, source: str, target: str, relation_info: RelationInfo) -> bool:
        pass
    
    @classmethod
    @abstractmethod
    def apply_effects(cls, graph: DcrGraph, original_source: str, effect_order: list[str]) -> DcrGraph:
        pass

    @classmethod
    @abstractmethod
    def update_executed_event_state(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        pass

    @classmethod
    @abstractmethod
    def update_graph_state(cls, graph: DcrGraph, execution_info: ExecutionInfo) -> DcrGraph:
        pass
    
    @classmethod
    @abstractmethod
    def perform_execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        pass

    @classmethod
    @abstractmethod
    def check_execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> bool:
        pass
    
    @classmethod
    @abstractmethod
    def execute(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        pass
    
    @classmethod
    @abstractmethod
    def is_accepting(cls, graph: DcrGraph, res: Set[str]) -> bool:
        pass