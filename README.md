# DCR4Py

DCR4Py is a DCR Graph extension of [PM4Py](https://processintelligence.solutions/), the Python process-mining library. It supports declarative process discovery, conformance checking, visualization, XML interchange, and data-aware Dynamic Condition Response (DCR) graphs.

## Capabilities

- Discover DCR graphs from event logs, including distributed, pending, and timed extensions.
- Check conformance with rule-based replay or optimal alignments.
- Import and export DCR Portal, DCR JS, and data-aware `XML_DCR_DATA` models.
- Visualize DCR graphs with Graphviz and convert DCR graphs to Petri nets.
- Model data-aware DCR graphs with typed input events, computed decision events, expression guards, and guarded conditions, responses, includes, excludes, milestones, and no-responses.
- Inject deterministic domain predicates into data-aware guards at runtime.

## Installation

Use a virtual environment, then install this checkout and its pinned dependencies:

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

The project uses the `pm4py` Python package namespace. Graph rendering additionally requires a local [Graphviz](https://graphviz.org/download/) installation.

## Quick Start

Discover a DCR graph and check the same log for conformance:

```python
import pm4py

log = pm4py.read_xes("path/to/event-log.xes")
graph, _ = pm4py.discover_dcr(log)

diagnostics = pm4py.conformance_dcr(
    log, graph, return_diagnostics_dataframe=True
)
print(diagnostics)
```

Build and execute a small data-aware DCR model. Input events receive a value at execution time; decision events evaluate expressions using values already held in the marking.

```python
from pm4py.objects.dcr.data.expressions import (
    DataType, INPUT_MARKER, const, event_ref, if_then_else, lt,
)
from pm4py.objects.dcr.data.obj import DataDcrGraph
from pm4py.objects.dcr.data.semantics import DataSemantics

graph = DataDcrGraph()
graph.events = {"Amount", "Decision"}
graph.labels = set(graph.events)
graph.label_map = {event: event for event in graph.events}
graph.marking.included = set(graph.events)
graph.event_types = {"Amount": DataType.INT, "Decision": DataType.INT}
graph.decisions = {
    "Amount": INPUT_MARKER,
    "Decision": if_then_else(lt(event_ref("Amount"), const(200)), const(1), const(2)),
}

DataSemantics.execute(graph, "Amount", input_value=150)
DataSemantics.execute(graph, "Decision")
print(graph.marking.event_values)  # {"Amount": 150, "Decision": 1}
```

## Documentation and Examples

- [API documentation](https://paul-cvp.github.io/dcr4pydocs/)
- [DCR tutorial notebook](notebooks/dcr_tutorial.ipynb)
- [Runnable DCR examples](examples/dcr_examples.py)
- [Data-aware DCR architecture](docs/data_dcr_architecture.md)
- [Data-aware XML format](docs/data_dcr_xml_format.md)
- [Predicate injection for guards](docs/data_dcr_predicate_injection.md)
- [Test suite](tests)

For a local Sphinx build, install the documentation dependencies, run `python -m setup` from `docs`, then run `make html`.

## License and Attribution

DCR4Py is licensed under the [GNU General Public License v3.0](LICENSE) and builds on PM4Py, developed by Process Intelligence Solutions and originally at Fraunhofer FIT.

## Citation

If you use DCR4Py in academic work, please cite:

> Hermansen, S. V., Jonsson, R., Kjeldsen, J. L., Slaats, T., Cosma, V. P., and Lopez, H. A. (2024). *DCR4Py: A PM4Py Library Extension for Declarative Process Mining in Python.* 6th International Conference on Process Mining. [Article](https://ceur-ws.org/Vol-3783/paper_353.pdf)

```bibtex
@inproceedings{hermansen2024dcr4py,
  title={DCR4Py: A PM4Py Library Extension for Declarative Process Mining in Python},
  author={Hermansen, Simon VH and J{\'o}nsson, Ragnar and Kjeldsen, Jonas L and Slaats, Tijs and Cosma, Vlad Paul and L{\'o}pez, Hugo A},
  booktitle={6th International Conference on Process Mining},
  year={2024},
  organization={CEUR-WS}
}
```

