from typing import Set
from datetime import datetime
from keyword import iskeyword
import re   # May be used in the evaluation of computations


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
        return effects
    
    @classmethod
    def getConstraints(cls, element: DcrElement, graph: DcrGraph) -> Set[DcrRelation]:
        constraints, _ = cls.getRelations(element, graph, "constraints")
        return constraints
    
    @classmethod
    def isEnabled(cls, element: DcrActivity | DcrSubprocess, graph: DcrGraph) -> bool:
        if not element.effectiveIncluded:
            return False
        if isinstance(element, DcrSubprocess) and element.childrenPending:
            return False
        constraints = cls.getConstraints(element, graph)
        for r in constraints:
            if not cls.constraintPasses(r.source, element, r.relationType, r.guard, graph):
                return False
        return True
    
    @classmethod
    def constraintPasses(cls, source: DcrElement, target: DcrElement, relationType: RelationType, guard: DcrComputation, graph: DcrGraph) -> bool:
        if isinstance(source, DcrNesting):
            res = True
            for child in source.children:
                res = res and cls.constraintPasses(child, target, relationType, guard, graph)
            return res
        if guard is None or cls.evaluateComputation(guard, graph, source, target):
            if relationType == RelationType.C and not source.executed:
                return False
            if relationType == RelationType.M and source.effectiveIncluded and source.effectivePending:
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
                return "(''.join(re.findall('Spawn\d+', " + element + ".ID)))"
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
                    for word in expression.split():
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
            cls.execute(activity, graph, event.input)
        else:
            raise Exception("Activity with ID {} is not enabled and cannot be executed".format(activity.ID))
    
    @classmethod
    def execute(cls, element: DcrActivity | DcrSubprocess, graph: DcrGraph, input=None):
        if element.takesInput and input is not None:
            element.data = input
        elif element.computation is not None:
            element.data = cls.evaluateComputation(element.computation, graph)
        graph.updatePending(element, False)
        element.executed = datetime.now()

        effects = cls.getEffects(element, graph)
        for r in sorted(effects, key=lambda r: r.relationType):
            cls.relateToTarget(element, r.target, r, graph)

        cls.executeSubprocessParent(element, graph)

    @classmethod
    def executeSubprocessParent(cls, element: DcrElement, graph: DcrGraph) -> int:
        parents = graph.getParents(element)
        sub = 0
        for parent in parents:
            if isinstance(parent, DcrSubprocess):
                sub += 1
                if cls.isEnabled(parent, graph):
                    cls.execute(parent, graph)
            elif isinstance(parent, DcrNesting):
                sub += cls.executeSubprocessParent(parent, graph)
            if sub:
                break
        return sub

    @classmethod
    def relateToTarget(cls, source: DcrElement, target: DcrElement, relation: DcrRelation, graph: DcrGraph):
        if target.isTemplate:
            return
        if isinstance(relation, DcrSpawn):
            if relation.guard is None or cls.evaluateComputation(relation.guard, graph, source, target):
                relation.spawned += 1
                cls.spawn(target, graph, relation.spawned)
        elif isinstance(target, DcrNesting):
            for child in target.children:
                cls.relateToTarget(source, child, relation, graph)
        else:
            if relation.guard is None or cls.evaluateComputation(relation.guard, graph, source, target):
                match relation.relationType:
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
                        target.data = relation.source.data

    @classmethod
    def spawn(cls, subgraph: DcrSubgraph, graph: DcrGraph, spawnNumber: int):
        spawnID = ''.join(re.findall('Spawn\d+', subgraph.ID))
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
                    if isinstance(o, DcrSpawn):
                        continue
                    elif o.source == template:
                        if isinstance(o.target, DcrSpawnContainer):
                            if isinstance(o, DcrEffect):
                                graph.relations.add(DcrEffect(o.relationType, elementDict[template], elementDict[o.target], o.guard))
                            else:
                                graph.relations.add(DcrConstraint(o.relationType, elementDict[template], elementDict[o.target], o.guard))
        
        graph.elements.update(elementDict.values())
        for template in elementDict:
            if isinstance(template, DcrSubgraph):
                for child in elementDict[template].children:
                    cls.makeTemplate(child, list(elementDict.values()))

    @classmethod
    def spawnElements(cls, element: DcrElement, graph: DcrGraph, spawnNumber: int, spawnID: str) -> dict[DcrElement, DcrElement]:
        spawns = {}

        if isinstance(element, DcrNesting | DcrSubprocess | DcrSubgraph):
            for child in element.children:
                spawns.update(cls.spawnElements(child, graph, spawnNumber, spawnID))
        
        if ''.join(re.findall('Spawn\d+', element.ID)) == spawnID:
            if type(element) is DcrSubgraph:
                spawns[element] = DcrSubgraph("{}Spawn{}".format(element.ID, spawnNumber))
            elif type(element) is DcrSpawnContainer:
                spawns[element] = element   ### maintains containers but also keeps subgraphs within subgraphs on the same containers across multiple instantiations of outer subgraph
            elif type(element) is DcrNesting:
                spawns[element] = DcrNesting("{}Spawn{}".format(element.ID, spawnNumber))
            elif type(element) is DcrSubprocess:
                spawns[element] = DcrSubprocess("{}Spawn{}".format(element.ID, spawnNumber), template=element)
                eventID = "e_{}Spawn{}".format(element.ID, spawnNumber)
                graph.activity_map[eventID] = spawns[element]
            else:
                spawns[element] = DcrActivity("{}Spawn{}".format(element.ID, spawnNumber), template=element)
                eventID = "e_{}Spawn{}".format(element.ID, spawnNumber)
                graph.activity_map[eventID] = spawns[element]

        return spawns
    
    @classmethod
    def makeTemplate(cls, element: DcrElement, spawned: list[DcrElement]):
        if not isinstance(element, DcrSpawnContainer) and element in spawned:
            element.isTemplate = True
        if isinstance(element, DcrParentElement):
          for child in element.children:
              cls.makeTemplate(child, spawned)

    @classmethod
    def isAccepting(cls, graph: DcrGraph) -> bool:
        for e in graph.elements:
            if isinstance(e, DcrActivity) and e.effectivePending and e.effectiveIncluded:
                return False
        return True