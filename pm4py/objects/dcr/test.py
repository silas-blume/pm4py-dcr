from obj import DcrGraph, dcr_template
from semantics import DcrSemantics
import pySFeel
import string
import decimal
import datetime

def to_feel(value):
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
            items = ', '.join(to_feel(item) for item in value)
            return f'[{items}]'

        case dict():
            items = ', '.join(f'{key}: {to_feel(val)}' for key, val in value.items())
            return f'{{{items}}}'

        case datetime.date() if not isinstance(value, datetime.datetime):
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

if __name__ == "__main__":
    
    template = dcr_template.copy()
    template['events'] = {'act1', 'act2', 'act3'}
    template['marking']['included'] = {'act1': {}, 'act2': {}, 'act3': {}, 'sub1': {}, 'sub2': {}}
    template['subprocesses'] = {'sub1': {'act1'}, 'sub2': {'sub1', 'act2'}}

    graph = DcrGraph(template)

    semantics = DcrSemantics.create_semantics_class('semantics', True)

    graph = semantics.execute(graph, 'act1', {})

    print(graph.returns[-1])