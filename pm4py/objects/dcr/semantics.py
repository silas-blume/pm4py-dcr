from typing import Set

from pm4py.objects.dcr.obj import DcrGraph

"""
We will implement the semantics according to the papers given in:
DCR 2011, and
Efficient optimal alignment between dynamic condition response graphs and traces
Following the schematic as the pm4py, by using definition function and no class function for this
"""


class DcrSemantics(object):
    """
        the semantics functions implemented is based on the paper by:

        Author: Thomas T. Hildebrandt and Raghava Rao Mukkamala,
        Title: Declarative Event-BasedWorkflow as Distributed Dynamic Condition Response Graphs
        publisher: Electronic Proceedings in Theoretical Computer Science. EPTCS, Open Publishing Association, 2010, pp. 59–73. doi: 10.4204/EPTCS.69.5.
        """
    @classmethod
    def is_enabled(cls, event, graph: DcrGraph) -> bool:
        """
        Verify that the given event is enabled for execution in the DCR graph

        Parameters
        ----------
        :param event: the instance of event being check for if enabled
        :param graph: DCR graph that it check for being enabled

        Returns
        -------
        :return: true if enabled, false otherwise
        """
        # check if event is enabled, calls function that returns a graph, of enabled events
        return event in cls.enabled(graph)

    @classmethod
    def enabled(cls, graph: DcrGraph) -> Set[str]:
        """
        Creates a list of enabled events, based on included events and conditions constraints met

        Parameters
        ----------
        :param graph: takes the current state of the DCR

        Returns
        -------
        :param res: set of enabled activities
        """
        # can be extended to check for milestones
        res = set(graph.marking.included)
        for e in set(graph.conditioned.keys()).intersection(res):
            if len(graph.conditioned[e].intersection(graph.marking.included.difference(
                    graph.marking.executed))) > 0:
                res.discard(e)
        for e in set(graph.milestoned.keys()).intersection(res):
            if len(graph.milestoned[e].intersection(graph.marking.included.intersection(
                    graph.marking.pending))) > 0:
                res.discard(e)
        return res
    
    @classmethod
    def get_sources(cls, graph: DcrGraph, sources: Set[str]):
        extended_sources = sources
        for source in sources:
            if source in graph.nested:
                extended_sources.update(graph.nested[source])
        if sources != extended_sources:
            return cls.get_sources(graph, extended_sources)
        return extended_sources
    
    @classmethod
    def apply_effect(cls, graph: DcrGraph, target, effect):
        if target in graph.nestings:
            for t_prime in graph.nestings[target]:
                graph = cls.apply_effect(graph, t_prime, effect)
        else:
          match effect:
              case 'e':
                  graph.marking.included.discard(target)
              case 'i':
                  graph.marking.included.add(target)
              case 'n':
                  graph.marking.pending.discard(target)
              case 'r':
                  graph.marking.pending.add(target)
              
        return graph

    @classmethod
    def execute(cls, graph: DcrGraph, event):
        """
        Function based on semantics of execution a DCR graph
        will update the graph according to relations of the executed activity

        can extend to allow of execution of milestone activity

        Parameters
        ----------
        :param graph: DCR graph
        :param event: the event being executed

        Returns
        ---------
        :return: DCR graph with updated marking
        """
        if event in graph.marking.pending:
            graph.marking.pending.discard(event)
        graph.marking.executed.add(event)

        sources = cls.get_sources(graph, set(event))

        for source in sources:
            if source in graph.excludes:
                for target in graph.excludes[source]:
                    cls.apply_effect(graph, target, 'e')

        for source in sources:
            if source in graph.includes:
                for target in graph.includes[source]:
                    cls.apply_effect(graph, target, 'i')

        for source in sources:
            if source in graph.noresponses:
                for target in graph.noresponses[source]:
                    cls.apply_effect(graph, target, 'n')

        for source in sources:
            if source in graph.responses:
                for target in graph.responses[source]:
                    cls.apply_effect(graph, target, 'r')

        return graph

    @classmethod
    def is_accepting(cls, graph: DcrGraph) -> bool:
        """
        Checks if the graph is accepting, no included events are pending

        Parameters
        ----------
        :param graph: DCR Graph

        Returns
        ---------
        :return: True if graph is accepting, false otherwise
        """
        res = graph.marking.pending.intersection(graph.marking.included)
        if len(res) > 0:
            return False
        else:
            return True