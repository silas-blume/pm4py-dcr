from typing import Set
import pySFeel
import string
import decimal
import datetime

from obj import DcrGraph, RelationInfo, ExecutionInfo
from semantics_interface import SemanticsInterface

class DataAndGuardSemanticsMixin(SemanticsInterface):

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
        edges += [('response', 'setValue')]
        return super().get_effect_order(edges)

    @classmethod
    def is_valid(cls, graph: DcrGraph, source: str, target: str, relation_info: RelationInfo) -> bool:
        guard = relation_info.get('guard')
        if guard is not None and not cls.compute_expression(graph, source, target, guard):
            return False
        return super().is_valid(graph, source, target, relation_info)
    
    @classmethod
    def apply_effects(cls, graph: DcrGraph, original_source: str, effect_order: list[str]) -> DcrGraph:
        if effect_order[0] == 'setValue':
            for source in cls.get_sources(graph, original_source, set()):
                for original_target, relation_info in graph.sets_value[original_source].items():
                    for target in cls.get_targets(graph, original_target, set()):
                        if cls.is_valid(graph, source, target, relation_info):
                            graph.marking.data[target]['data'] = cls.compute_expression(graph, source, target, relation_info.get('expression'))

        return super().apply_effects(graph, original_source, effect_order)

    @classmethod
    def update_executed_event_state(cls, graph: DcrGraph, event: str, execution_info: ExecutionInfo) -> DcrGraph:
        data_info = graph.marking.data.get(event, {})

        is_input_event = data_info.get('input', False)
        if is_input_event:
            input = execution_info.get('input')
            if input is not None:
                graph.marking.data[event]['data'] = cls.compute_expression(graph, event, '', input)
        else:
            expression = data_info.get('expression')
            if expression is not None:
                graph.marking.data[event]['data'] = cls.compute_expression(graph, event, '', expression)
        # compute expression if any
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
    
    @classmethod
    def to_feel(cls, value):
        """
        Serialize a Python value into a valid FEEL expression string.
        """
        match value:

            case str():
                escaped = value.replace('"', '\\"')
                return f'"{escaped}"'

            case bool():
                return 'true' if value else 'false'

            case None:
                return 'null'

            case int() | float() | decimal.Decimal:
                return str(value)

            case list():
                items = ', '.join(cls.to_feel(item) for item in value)
                return f'[{items}]'

            case dict():
                items = ', '.join(f'{key}: {cls.to_feel(val)}' for key, val in value.items())
                return f'{{{items}}}'

            case datetime.date():
                return f'date("{value.isoformat()}")'

            case datetime.time():
                return f'time("{value.isoformat()}")'

            case datetime.datetime():
                return f'date and time("{value.isoformat()}")'

            case datetime.timedelta():
                total_seconds = int(value.total_seconds())
                days, remainder = divmod(total_seconds, 86400)
                hours, remainder = divmod(remainder, 3600)
                minutes, seconds = divmod(remainder, 60)

                duration = 'P'
                if days:
                    duration += f'{days}D'
                if hours or minutes or seconds:
                    duration += 'T'
                if hours:
                    duration += f'{hours}H'
                if minutes:
                    duration += f'{minutes}M'
                if seconds:
                    duration += f'{seconds}S'

                return f'duration("{duration}")'

            case _:
                raise TypeError(f"Unsupported type for FEEL serialization: {type(value)}")
            
    @classmethod
    def parse_argument(cls, graph: DcrGraph, source: str, target: str, argument: str):
        parts = argument.split('.')
        if len(parts) == 1:
            # What could this reference?
            raise ValueError(f"Expression argument doesn't match data in graph: {argument}. To access the data of an event, use <event_name>.data, not just <event_name>")
        
        label = parts[0]
        match label:
            case 'source':
                event = source
            case 'target':
                event = target
            case 'self':
                event = source
            case _:
                if label in graph.events:
                    event = label
                else:
                    event = graph.get_event(label)
        if event is None:
            raise ValueError(f"Expression argument doesn't match event or label in graph: {label}")
        
        match parts[1]:
            case 'data':
                res = graph.marking.data[event].get('data')
            case _:
                res = None

        if len(parts) > 2:
            for index in parts[2:]:
                if res is None:
                    break
                res = res.get(index)

        # Currently allows returning None
        return res
    
    @classmethod
    def compute_expression(cls, graph: DcrGraph, source: str, target: str, expression: str):
        parser = pySFeel.SFeelParser()
        formatter = string.Formatter()

        arguments = [fname for _, fname, _, _ in formatter.parse(expression) if fname]
        params = {arg: cls.parse_argument(graph, source, target, arg) for arg in arguments}

        res = parser.sFeelParse(expression.format(**params))
        if res is not None:
            meta, result = res
            if 'errors' in meta:
                raise ValueError(f'Error parsing expression: "{expression}", exception: {meta["errors"]}')
            return result
        raise ValueError(f'Error parsing expression: "{expression}"')