from typing import List, Set

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
        for e in set(graph.conditions.keys()).intersection(res):
            if len(graph.conditions[e].intersection(graph.marking.included.difference(
                    graph.marking.executed))) > 0:
                res.discard(e)
        return res

    @classmethod
    def enablement_blockers(cls, event: str, graph: DcrGraph) -> List[str]:
        """
        Explain why ``event`` is not enabled, mirroring the exact blocking
        conditions used by :meth:`enabled`. An empty list means nothing in
        this (base, unguarded-conditions-only) scope blocks the event --
        subclasses that add more relation types (milestones, guards) extend
        this with their own checks.

        Parameters
        ----------
        :param event: the event being explained
        :param graph: DCR graph to check against

        Returns
        -------
        :return: list of human-readable blocker descriptions (empty if none)
        """
        blockers: List[str] = []
        included = graph.marking.included

        if event not in included:
            blockers.append("event is excluded (not included in current marking)")

        unmet = sorted(
            graph.conditions.get(event, set()) & included - graph.marking.executed
        )
        if unmet:
            blockers.append(f"unmet condition(s): {', '.join(unmet)}")

        return blockers

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
        # each event is called for execution is called
        if event in graph.marking.pending:
            graph.marking.pending.discard(event)
        graph.marking.executed.add(event)

        # the following if statements are used to provide to update DCR graph
        # depending on prime event structure within conditions relations
        if event in graph.excludes:
            for e_prime in graph.excludes[event]:
                graph.marking.included.discard(e_prime)

        if event in graph.includes:
            for e_prime in graph.includes[event]:
                graph.marking.included.add(e_prime)

        if event in graph.responses:
            for e_prime in graph.responses[event]:
                graph.marking.pending.add(e_prime)

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