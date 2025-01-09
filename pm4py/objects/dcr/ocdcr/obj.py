from enum import IntEnum
from typing import Set, Dict, Callable
from datetime import datetime
from abc import ABC, abstractmethod


class RelationType(IntEnum):
    S = 1 # spawn
    E = 2 # exclude
    I = 3 # include
    N = 4 # no-response
    R = 5 # response
    V = 6 # value
    C = 7 # condition
    M = 8 # milestone

class DcrEvent:
    
    def __init__(self, id, input=None):
        self.__id = id
        self.__input = input

    @property
    def ID(self) -> str:
        return self.__id
    
    @property
    def input(self) -> any:
        return self.__input
    

type DcrExpression = str | int | float | tuple[str, str]
type DcrComputation = list[DcrExpression]

class DcrElement(ABC):
    
    def __init__(self, id, template=None):
        self.__id = id
        self.__parentsIncluded = True if template is None else template.parentsIncluded
        self.__isTemplate = False

    @property
    def ID(self) -> str:
        return self.__id
    
    @ID.setter
    def ID(self, value: str):
        self.__id = value

    @property
    def parentsIncluded(self) -> bool:
        return self.__parentsIncluded
    
    @parentsIncluded.setter
    def parentsIncluded(self, value: bool):
        self.__parentsIncluded = value

    @property
    @abstractmethod
    def effectiveIncluded(self) -> bool:
        pass

    @property
    @abstractmethod
    def effectivePending(self) -> bool:
        pass

    @property
    def isTemplate(self) -> bool:
        return self.__isTemplate
    
    @isTemplate.setter
    def isTemplate(self, value: bool):
        self.__isTemplate = value

    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, value: object) -> bool:
        return hash(self) == hash(value)
    
    def __str__(self) -> str:
        return self.ID


class DcrActivity(DcrElement):
    
    def __init__(self, id, included=True, pending=False, computation: DcrComputation=None, takesInput=False, template=None, **kwargs):
        super().__init__(id, template=template, **kwargs)
        self.__included = included if template is None else template.included
        self.__pending = pending if template is None else template.pending
        self.__executed = None # set as None or a datetime denoting execution time. Not currently used but for compatability with timed graphs.
        self.__computation = computation if template is None else template.computation
        self.__takesInput = takesInput if template is None else template.takesInput
        self.__data = None

    @property
    def included(self) -> bool:
        return self.__included
    
    @included.setter
    def included(self, value: bool):
        self.__included = value

    @property
    def effectiveIncluded(self) -> bool:
        return self.included and self.parentsIncluded and not self.isTemplate

    @property
    def pending(self) -> bool:
        return self.__pending
    
    @pending.setter
    def pending(self, value: bool):
        self.__pending = value
    
    @property
    def effectivePending(self) -> bool:
        return self.pending and not self.isTemplate

    @property
    def executed(self) -> datetime:
        return self.__executed
    
    @executed.setter
    def executed(self, value: datetime):
        self.__executed = value

    @property
    def computation(self) -> DcrComputation:
        return self.__computation
    
    @property
    def takesInput(self) -> bool:
        return self.__takesInput

    @property
    def data(self) -> any:
        return self.__data
    
    @data.setter
    def data(self, value: any):
        self.__data = value


class DcrParentElement(DcrElement):
    
    def __init__(self, id, children=None, template = None):
        super().__init__(id, template)
        self.__children = set() if children is None else children
        self.__childrenPending = False if template is None else template.childrenPending

    @property
    def children(self) -> Set[DcrElement]:
        return self.__children
    
    @children.setter
    def children(self, value: Set[DcrElement]):
        self.__children = value

    @property
    def childrenPending(self) -> bool:
        return self.__childrenPending
    
    @childrenPending.setter
    def childrenPending(self, value: bool):
        self.__childrenPending = value

    @property
    def effectivePending(self) -> bool:
        return self.childrenPending and not self.isTemplate
    
    @property
    def included(self) -> bool:
        return True

    @property
    def effectiveIncluded(self) -> bool:
        return self.parentsIncluded and not self.isTemplate
    

class DcrSubprocess(DcrActivity, DcrParentElement):
    
    def __init__(self, id, children=None, included=True, pending=False, computation=None, template=None):
        super().__init__(id=id, included=included, pending=pending, computation=computation, takesInput=False, template=template, children=children)
    
    @property
    def effectivePending(self) -> bool:
        return (self.pending or self.childrenPending) and not self.isTemplate
    

class DcrNesting(DcrParentElement):
    
    def __init__(self, id, children=None, template = None):
        super().__init__(id, children, template)


class DcrSubgraph(DcrParentElement):
    
    def __init__(self, id, children=None, template = None):
        super().__init__(id, children, template)


class DcrSpawnContainer(DcrNesting):
    
    def __init__(self, id, children=None, template = None):
        super().__init__(id, children, template)


class DcrRelation:
    
    def __init__(self, relationType: RelationType, source: DcrElement, target: DcrElement, guard: DcrComputation=None, forAll=False):
        self.__relationType = relationType
        self.__source = source
        self.__target = target
        self.__guard = guard
        self.__forAll = forAll

    @property
    def relationType(self) -> RelationType:
        return self.__relationType
    
    @relationType.setter
    def relationType(self, value: RelationType):
        self.__relationType = value

    @property
    def source(self) -> DcrElement:
        return self.__source
    
    @source.setter
    def source(self, value: DcrElement):
        self.__source = value

    @property
    def target(self) -> DcrElement:
        return self.__target
    
    @target.setter
    def target(self, value: DcrElement):
        self.__target = value

    @property
    def guard(self) -> DcrComputation:
        return self.__guard
    
    @guard.setter
    def guard(self, value: DcrComputation):
        self.__guard = value

    @property
    def forAll(self) -> bool:
        return self.__forAll
    
    @forAll.setter
    def forAll(self, value: bool):
        self.__forAll = value
    
    def __repr__(self):
        return "Relation type: " + str(self.relationType) + ", Source: " + str(self.source) + ", Target: " + str(self.target) + ", Guard: " + str(self.guard)

    def __hash__(self) -> int:
        return hash(repr(self))
    
    def __eq__(self, value: object) -> bool:
        return hash(self) == hash(value)


class DcrEffect(DcrRelation):
    
    def __init__(self, relationType, source, target, guard=None, forAll=False):
        if relationType not in [RelationType.I, RelationType.E, RelationType.R, RelationType.N, RelationType.V, RelationType.S]:
            raise Exception("Effects must be include, exclude, response, noresponse, setValue or spawn")
        if relationType == RelationType.S and type(self) is not DcrSpawn:
            raise Exception("Spawn relations must be instances of DcrSpawn, not DcrEffect directly")
        super().__init__(relationType, source, target, guard, forAll)
    

class DcrSpawn(DcrEffect):
    
    def __init__(self, source, target, guard=None, forAll=False):
        super().__init__(RelationType.S, source, target, guard, forAll)
        self.__spawned = 0
    
    @property
    def spawned(self) -> int:
        return self.__spawned
    
    @spawned.setter
    def spawned(self, value: int):
        self.__spawned = value


class DcrConstraint(DcrRelation):
    
    def __init__(self, relationType, source, target, guard=None, forAll=False):
        if relationType not in [RelationType.C, RelationType.M]:
            raise Exception("Constraints must be condition or milestone")
        super().__init__(relationType, source, target, guard, forAll)


class DcrGraph:
    
    def __init__(self, id, events=set(), elements=set(), activityMap={}, relations=set(), template=None):
        self.__id = id
        self.__events = events if template is None else template.events
        self.__elements = elements if template is None else template.elements
        self.__activityMap = activityMap if template is None else template.labelMapping
        self.__relations = relations if template is None else template.relations

        self.initiateGraph()

    @property
    def ID(self) -> str:
        return self.__id
    
    @ID.setter
    def ID(self, value: str):
        self.__id = value

    @property
    def events(self) -> Set[DcrEvent]:
        return self.__events

    @events.setter
    def events(self, value: Set[DcrEvent]):
        self.__events = value

    @property
    def elements(self) -> Set[DcrElement]:
        return self.__elements

    @elements.setter
    def elements(self, value: Set[DcrElement]):
        self.__elements = value

    @property
    def activityMap(self) -> Dict[str, DcrActivity]:
        return self.__activityMap

    @activityMap.setter
    def activityMap(self, value: Dict[str, DcrActivity]):
        self.__activityMap = value

    @property
    def relations(self) -> Set[DcrRelation]:
        return self.__relations
    
    @relations.setter
    def relations(self, value: Set[DcrRelation]):
        self.__relations = value

    def getParents(self, element: DcrElement) -> Set[DcrParentElement]:
        parents = set()
        for e in self.elements:
            if isinstance(e, DcrParentElement) and element in e.children:
                parents.add(e)
        return parents
    
    def updateIncluded(self, element: DcrElement, value: bool=None):
        if value is not None:
            element.included = value
        if isinstance(element, DcrParentElement):
          for child in element.children:
              if not element.effectiveIncluded and child.parentsIncluded:
                  child.parentsIncluded = False
                  self.updateIncluded(child)
              else:
                  oldState = child.parentsIncluded
                  child.parentsIncluded = True
                  parents = self.getParents(child)
                  for parent in parents:
                      child.parentsIncluded = child.parentsIncluded and parent.effectiveIncluded
                  if child.parentsIncluded != oldState:
                      self.updateIncluded(child)
    
    def updatePending(self, element: DcrElement, value: bool=None):
        if value is not None:
            element.pending = value
        parents = self.getParents(element)
        for parent in parents:
            if  element.effectivePending and element.included and not parent.childrenPending:
                parent.childrenPending = True
                self.updatePending(parent)
            else:
                oldState = parent.childrenPending
                parent.childrenPending = False
                for child in parent.children:
                    parent.childrenPending = parent.childrenPending or child.effectivePending and child.included
                if parent.childrenPending != oldState:
                    self.updatePending(parent)
    
    def hasAsParent(self, child: DcrElement, element: DcrElement) -> bool:
        parents = self.getParents(child)
        if element in parents:
            return True
        else:
            res = False
            for parent in parents:
                res = res or self.hasAsParent(parent, element)
            return res
    
    def initiateSpawnContainers(self, element: DcrElement, subgraph: DcrSubgraph) -> Set[DcrSpawnContainer]:
        element.isTemplate = True
        containers = set()
        container = DcrSpawnContainer(element.ID + "Container", {element})
        containers.add(container)
        for r in self.relations:
            if r.source == element and (r.forAll or not self.hasAsParent(r.target, subgraph)):
                r.source = container
            if r.target == element and (r.forAll or not self.hasAsParent(r.source, subgraph)):
                r.target = container
        if isinstance(element, DcrNesting | DcrSubprocess):
            for child in element.children:
                containers.update(self.initiateSpawnContainers(child, subgraph))
        return containers

    def getSubprocessParents(self, element: DcrElement) -> Set[DcrSubprocess]:
        subprocesses = set()
        parents = self.getParents(element)
        for parent in parents:
            if isinstance(parent, DcrSubprocess):
                subprocesses.add(parent)
            else:
                subprocesses.update(self.getSubprocessParents(parent))
        return subprocesses

    def initiateGraph(self):
        spawnContainers = set()
        for element in self.elements:
            if len(self.getSubprocessParents(element)) > 1:
                raise Exception("Element with ID {} is part of more than one subprocesses".format(element.ID))

            if isinstance(element, DcrSubgraph):
                for relation in self.relations:
                    if relation.target == element and not isinstance(relation, DcrSpawn):
                        raise Exception("Subgraph with ID {} is the target of a non-spawn relation".format(element.ID))
                    if relation.source == element:
                        raise Exception("Subgraph with ID {} is the source of one or more relations and should not be".format(element.ID))
                containers = set()
                for child in element.children:
                    containers.update(self.initiateSpawnContainers(child, element))
                element.children = containers
                spawnContainers.update(containers)
            if isinstance(element, DcrActivity):
                if not element.effectiveIncluded:
                    self.updateIncluded(element)
                if element.effectivePending:
                    self.updatePending(element)
        self.elements.update(spawnContainers)
        for relation in self.relations:
            if isinstance(relation, DcrSpawn) and not isinstance(relation.target, DcrSubgraph):
                raise Exception("Non-subgraph element with ID {} is the target of a spawn relation".format(relation.target.ID))
            

    def getEventID(self, activity: DcrActivity) -> str:
        for eventID, dcrActivity in self.activityMap.items():
            if activity == dcrActivity:
                return eventID

    def getActivity(self, eventID: str) -> DcrActivity:
        return self.activityMap[eventID]
    
    def getElementFromID(self, ID: str) -> DcrElement:
        for e in self.elements:
            if e.ID == ID:
                return e
        return None

    def getConstraints(self) -> int:
        return len(self.__relations)