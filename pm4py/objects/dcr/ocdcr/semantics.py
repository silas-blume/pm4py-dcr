from typing import Set
from datetime import datetime
from keyword import iskeyword
import re
import logging


from obj import DcrGraph, DcrElement, DcrParentElement, DcrNesting, DcrSubprocess, DcrSubgraph, DcrSpawnContainer, DcrActivity, DcrRelation, DcrEffect, DcrSpawn, DcrConstraint, RelationType, DcrExpression, DcrComputation, DcrEvent


class DcrSemantics:

    @classmethod
    def getRelations(cls, element: DcrElement, graph: DcrGraph, yields: str=None) -> tuple[Set[DcrRelation], Set[DcrRelation]]:
        incoming = set()
        outgoing = set()
        for r in graph.relations:
            if r.target == element and (yields != "constraints" or isinstance(r, DcrConstraint)):
                incoming.add(r)
            if r.source == element and (yields != "effects" or isinstance(r, DcrEffect)):
                outgoing.add(r)
        parents = graph.getParents(element)
        for parent in parents:
            if isinstance(parent, DcrNesting):
                i, o = cls.getRelations(parent, graph, yields)
                incoming.update(i)
                outgoing.update(o)
        return incoming, outgoing
    
    @classmethod
    def getEffects(cls, element: DcrElement, graph: DcrGraph) -> Set[DcrRelation]:
        _, effects = cls.getRelations(element, graph, "effects")
        remove = set()
        for e in effects:
            if isinstance(e.source, DcrSpawnContainer) and not isinstance(e.target, DcrSpawnContainer) and cls.getTopSubgraph(e.target, graph) is cls.getTopSubgraph(e.source, graph) and not cls.getSpawnID(element).startswith(cls.getSpawnID(e.target)):
                remove.add(e)
        return effects - remove
    
    @classmethod
    def getConstraints(cls, element: DcrElement, graph: DcrGraph) -> Set[DcrRelation]:
        constraints, _ = cls.getRelations(element, graph, "constraints")
        for sub in graph.getSubprocessParents(element):
            constraints.update(cls.getConstraints(sub, graph))
        remove = set()
        for c in constraints:
            if isinstance(c.source, DcrSpawnContainer) and not isinstance(c.target, DcrSpawnContainer) and cls.getTopSubgraph(c.target, graph) is cls.getTopSubgraph(c.source, graph) and not cls.getSpawnID(c.source).startswith(cls.getSpawnID(element)):
                remove.add(c)
        return constraints - remove
    
    @classmethod
    def isEnabled(cls, element: DcrActivity | DcrSubprocess, graph: DcrGraph) -> bool:
        if not element.effectiveIncluded:
            return False
        if isinstance(element, DcrSubprocess) and element.childrenPending:
            return False
        constraints = cls.getConstraints(element, graph)
        for r in constraints:
            if not cls.constraintPasses(r.source, element, r, graph):
                return False
        return True
    
    @classmethod
    def constraintPasses(cls, source: DcrElement, target: DcrElement, constraint: DcrConstraint, graph: DcrGraph) -> bool:
        if target is constraint.target and isinstance(target, DcrSpawnContainer) and not isinstance(constraint.source, DcrSpawnContainer) and cls.getTopSubgraph(constraint.source, graph) is cls.getTopSubgraph(constraint.target, graph):
            for child in target.children:
                if cls.getSpawnID(child) == cls.getSpawnID(source):
                    return cls.constraintPasses(source, child, constraint, graph)
        if isinstance(source, DcrNesting):
            res = True
            for child in source.children:
                res = res and cls.constraintPasses(child, target, constraint, graph)
            return res
        if source.effectiveIncluded and (constraint.guard is None or cls.evaluateComputation(constraint.guard, graph, source, target)):
            if constraint.relationType == RelationType.C and not source.executed:
                return False
            if constraint.relationType == RelationType.M and source.effectivePending:
                return False
        return True
    
    @classmethod
    def parseAttribute(cls, element: str, attribute: str) -> any:
        match attribute:
            case "id":
                return element + ".ID"
            case "included":
                return element + ".effectiveIncluded"
            case "pending":
                return element + ".effectivePending and " + element + ".effectiveIncluded"  ### Should this care if included?
            case "executed":
                return element + ".executed"
            case "enabled":
                return "cls.isEnabled(" + element + ", graph)"
            case "computation":
                return element + ".computation"
            case "data":
                return element + ".data"
            case "children":
                return element + ".children"
            case "instance":
                return "(cls.getSpawnID(" + element + "))"
            case _:
                return None
    
    @classmethod
    def parseExpression(cls, expression: DcrExpression):
        operators = ["+", "-", "*", "/", "==", "<", ">", "<=", ">=", "and", "or", "not", "is", "in", "(", ")", "len"]
        match expression:
            case (e1, e2):
                if e1 in ["source", "target"]:
                    return cls.parseAttribute(e1, e2)
                else:
                    return cls.parseAttribute("graph.getElementFromID('{}')".format(e1), e2)
            case str():
                if expression in operators:
                    return expression
                elif expression == "inInstance":
                    return ".startswith"
                else:
                    for word in re.split(" |(|)|.", expression):
                        if iskeyword(word):
                            return None
                    return expression
            case int():
                return str(expression)
            case float():
                return str(expression)
    
    @classmethod
    def evaluateComputation(cls, computation: DcrComputation, graph: DcrGraph, source: DcrElement=None, target: DcrElement=None) -> any:
    # Unaccessed parameters may be used for evaluation of final string.
        for i, expression in enumerate(computation):
            computation[i] = cls.parseExpression(expression)
        executable = " ".join(computation)
        return eval(executable)

    @classmethod
    def executeEvent(cls, event: DcrEvent, graph: DcrGraph):
        activity = graph.getActivity(event.ID)
        if cls.isEnabled(activity, graph):
            if event.executionTime is None:
                event.executionTime = datetime.now()
            graph.events.append(event)
            cls.execute(activity, graph, event.input, event.executionTime)
        else:
            raise Exception("Activity with ID {} is not enabled and cannot be executed".format(activity.ID))
    
    @classmethod
    def execute(cls, element: DcrActivity | DcrSubprocess, graph: DcrGraph, input=None, executionTime=None):
        if element.takesInput and input is not None:
            element.data = input
        elif element.computation is not None:
            element.data = cls.evaluateComputation(element.computation, graph)
        graph.updatePending(element, False)
        element.executed = datetime.now() if executionTime is None else executionTime

        effects = cls.getEffects(element, graph)
        for r in sorted(effects, key=lambda r: r.relationType):
            cls.relateToTarget(element, r.target, r, graph)

        cls.executeSubprocessParent(element, graph)

    @classmethod
    def executeSubprocessParent(cls, element: DcrElement, graph: DcrGraph) -> int:
        parents = graph.getParents(element)
        sub = False
        for parent in parents:
            if isinstance(parent, DcrSubprocess):
                sub = True
                if cls.isEnabled(parent, graph):
                    cls.execute(parent, graph)
            elif isinstance(parent, DcrNesting):
                sub = cls.executeSubprocessParent(parent, graph)
            if sub:
                break
        return sub

    @classmethod
    def relateToTarget(cls, source: DcrElement, target: DcrElement, effect: DcrEffect, graph: DcrGraph):
        if target.isTemplate:
            return
        if target is effect.target and isinstance(target, DcrSpawnContainer) and not isinstance(effect.source, DcrSpawnContainer) and cls.getTopSubgraph(effect.source, graph) is cls.getTopSubgraph(effect.target, graph):
            for child in target.children:
                if cls.getSpawnID(child) == cls.getSpawnID(source):
                    cls.relateToTarget(source, child, effect, graph)
                    return
        elif isinstance(effect, DcrSpawn):
            if effect.guard is None or cls.evaluateComputation(effect.guard, graph, source, target):
                effect.spawned += 1
                cls.spawn(target, graph, effect.spawned)
        elif isinstance(target, DcrNesting):
            for child in target.children:
                cls.relateToTarget(source, child, effect, graph)
        else:
            if effect.guard is None or cls.evaluateComputation(effect.guard, graph, source, target):
                match effect.relationType:
                    case RelationType.I:
                        graph.updateIncluded(target, True)
                        if target.pending:
                            graph.updatePending(target)
                    case RelationType.E:
                        graph.updateIncluded(target, False)
                        if target.pending:
                            graph.updatePending(target)
                    case RelationType.R:
                        if target.included:
                            graph.updatePending(target, True)
                        else:
                            target.pending = True
                    case RelationType.N:
                        if target.included:
                            graph.updatePending(target, False)
                        else:
                            target.pending = False
                    case RelationType.V:
                        target.data = cls.evaluateComputation(effect.value, graph, source, target)

    @classmethod
    def spawn(cls, subgraph: DcrSubgraph, graph: DcrGraph, spawnNumber: int):
        spawnID = cls.getSpawnID(subgraph)
        elementDict = {}
        for spawnContainer in subgraph.children:
            elementDict[spawnContainer] = spawnContainer
            for element in spawnContainer.children:
                elementDict.update(cls.spawnElements(element, graph, spawnNumber, spawnID))

        for template in elementDict:
            if isinstance(template, DcrParentElement):
                children = set()
                for child in template.children:
                    if child in elementDict:
                        children.add(elementDict[child])
                elementDict[template].children.update(children)

            if template is not elementDict[template]:
                incoming, outgoing = cls.getRelations(template, graph)
                for i in incoming:
                    if i.target == template:
                        if isinstance(i, DcrSpawn):
                            graph.relations.add(DcrSpawn(elementDict[i.source], elementDict[template], i.guard))
                        elif isinstance(i, DcrEffect):
                            graph.relations.add(DcrEffect(i.relationType, elementDict[i.source], elementDict[template], i.guard))
                        else:
                            graph.relations.add(DcrConstraint(i.relationType, elementDict[i.source], elementDict[template], i.guard))
                for o in outgoing:
                    if o.source == template:
                        if isinstance(o.target, DcrSpawnContainer):
                            if isinstance(o, DcrEffect):
                                graph.relations.add(DcrEffect(o.relationType, elementDict[template], elementDict[o.target], o.guard))
                            else:
                                graph.relations.add(DcrConstraint(o.relationType, elementDict[template], elementDict[o.target], o.guard))
        
        graph.elements.update(elementDict.values())
        for template in elementDict:
            if isinstance(template, DcrSubgraph):
                for child in elementDict[template].children:
                    cls.makeTemplate(child, set(elementDict.values()))
                    cls.spawnSubContainers(child, set(elementDict.values()), graph)

    @classmethod
    def spawnElements(cls, element: DcrElement, graph: DcrGraph, spawnNumber: int, spawnID: str) -> dict[DcrElement, DcrElement]:
        spawns = {}

        if isinstance(element, DcrNesting | DcrSubprocess | DcrSubgraph):
            for child in element.children:
                spawns.update(cls.spawnElements(child, graph, spawnNumber, spawnID))
        
        if cls.getSpawnID(element) == spawnID: # ensures that we only spawn template elements from the correct spawn level
            if type(element) is DcrSubgraph:
                spawns[element] = DcrSubgraph("{}Spawn{}".format(element.ID, spawnNumber))
            elif type(element) is DcrSpawnContainer:
                spawns[element] = element # maintains containers and also keeps subgraphs within subgraphs on the same containers across multiple instantiations of outer subgraph
            elif type(element) is DcrNesting:
                spawns[element] = DcrNesting("{}Spawn{}".format(element.ID, spawnNumber))
            elif type(element) is DcrSubprocess:
                spawns[element] = DcrSubprocess("{}Spawn{}".format(element.ID, spawnNumber), template=element)
            else:
                spawns[element] = DcrActivity("{}Spawn{}".format(element.ID, spawnNumber), template=element)
                eventID = "e_{}Spawn{}".format(element.ID, spawnNumber)
                graph.activityMap[eventID] = spawns[element]

        return spawns
    
    @classmethod
    def getSpawnID(cls, element: DcrElement):
        return ''.join(re.findall('Spawn\d+', element.ID))
    
    @classmethod
    def makeTemplate(cls, element: DcrElement, spawned: Set[DcrElement]):
        if not isinstance(element, DcrSpawnContainer) and element in spawned:
            element.isTemplate = True
        if isinstance(element, DcrParentElement):
          for child in element.children:
              cls.makeTemplate(child, spawned)

    @classmethod
    def spawnSubContainers(cls, container: DcrSpawnContainer, spawned: Set[DcrElement], graph: DcrGraph):
        for child in container.children:
            if child in spawned:
                newChild = child
                break
        subContainer = DcrSpawnContainer(newChild.ID + "Container", {newChild})
        graph.elements.add(subContainer)
        container.children.remove(newChild)
        container.children.add(subContainer)
        if isinstance(newChild, DcrNesting | DcrSubprocess):
            for child in newChild.children:
                if isinstance(child, DcrSpawnContainer):
                    cls.spawnSubContainers(child, spawned, graph)


    @classmethod
    def getTopSubgraph(cls, element: DcrElement, graph: DcrGraph, topSub=None):
        parents = graph.getParents(element)
        for parent in parents:
            if isinstance(parent, DcrSubgraph):
                topSub = parent
                break
        if parents:
            return cls.getTopSubgraph(list(parents)[0], graph, topSub)
        return topSub