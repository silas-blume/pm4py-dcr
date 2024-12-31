from enum import Flag
from typing import Set, Dict, Callable
from datetime import datetime


class RelationType(Flag): ### ORDER REMAINING 5 EFFECTS ACCORDING TO ORDER OF APPLICATION ###
    S = 'spawn'
    E = 'exclude'
    I = 'include'
    N = 'noResponse'
    R = 'response'
    V = 'setValue'
    C = 'condition'
    M = 'milestone'
    EFFECTS = I | E | R | N | S | V
    CONSTRAINTS = C | M

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
    

class DcrExpression:
    
    def __init__(self, reference, value, operator=None, additional=None):
        self.__reference = reference
        self.__value = value
        self.__operator = operator
        self.__additional = additional

    @property
    def reference(self) -> str:
        return self.__reference
    
    @property
    def value(self) -> any:
        return self.__value
    
    @property
    def operator(self) -> str:
        return self.__operator
    
    @property
    def additional(self) -> 'DcrExpression':
        return self.__additional

class DcrElement:
    
    def __init__(self, id, template=None, isTemplate=False):
        self.__id = id
        self.__parentsIncluded = True if template is None else template.parentsIncluded
        self.__childrenPending = False if template is None else template.childrenPending
        self.__template = isTemplate

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
    def childrenPending(self) -> bool:
        return self.__childrenPending
    
    @childrenPending.setter
    def childrenPending(self, value: bool):
        self.__childrenPending = value

    @property
    def included(self) -> bool:
        return self.parentsIncluded

    @property
    def pending(self) -> bool:
        return self.childrenPending

    @property
    def isTemplate(self) -> bool:
        return self.__template
    
    @isTemplate.setter
    def isTemplate(self, value: bool):
        self.__template = value

    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, value: object) -> bool:
        return hash(self) == hash(value)
    
    def __str__(self) -> str:
        return self.ID


class DcrActivity(DcrElement):
    
    def __init__(self, id, expression=None, takesInput=False, template=None, isTemplate=False):
        super().__init__(id, template, isTemplate)
        self.__included = True if template is None else template.included
        self.__pending = False if template is None else template.pending
        self.__executed = None if template is None else template.executed # set as None or a datetime denoting execution time. Not currently used but for compatability with timed graphs.
        self.__expression = expression if template is None else template.expression
        self.__takesInput = takesInput if template is None else template.takesInput
        self.__data = None

    @property
    def included(self) -> bool:
        return self.__included and self.parentsIncluded
    
    @included.setter
    def included(self, value: bool):
        self.__included = value

    @property
    def pending(self) -> bool:
        return self.__pending or self.childrenPending
    
    @pending.setter
    def pending(self, value: bool):
        self.__pending = value

    @property
    def executed(self) -> datetime:
        return self.__executed
    
    @executed.setter
    def executed(self, value: datetime):
        self.__executed = value

    @property
    def expression(self) -> DcrExpression:
        return self.__expression
    
    @property
    def takesInput(self) -> bool:
        return self.__takesInput

    @property
    def data(self) -> any:
        return self.__data
    
    @data.setter
    def data(self, value: any):
        self.__data = value


class DcrSubprocess(DcrActivity):
    
    def __init__(self, id, children=None, expression=None, takesInput=False, template=None, isTemplate=False):
        super().__init__(id, expression, takesInput, template, isTemplate)
        self.__children = set() if children is None else children

    @property
    def children(self) -> Set[DcrElement]:
        return self.__children
    
    @children.setter
    def children(self, value: Set[DcrElement]):
        self.__children = value
    

class DcrNesting(DcrElement):
    
    def __init__(self, id, children=None, isTemplate=False):
        super().__init__(id, isTemplate=isTemplate)
        self.__children = set() if children is None else children

    @property
    def children(self) -> Set[DcrElement]:
        return self.__children
    
    @children.setter
    def children(self, value: Set[DcrElement]):
        self.__children = value


class DcrSubgraph(DcrNesting):
    
    def __init__(self, id, children=None):
        super().__init__(id, children, True)


class DcrSpawnContainer(DcrNesting):
    
    def __init__(self, id, children=None):
        super().__init__(id, children, False)


class DcrRelation:
    
    def __init__(self, type, source, target, guard=None, forAll=False):
        self.__relationType = type
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
    def guard(self) -> DcrExpression:
        return self.__guard
    
    @guard.setter
    def guard(self, value: DcrExpression):
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
    

class DcrSpawn(DcrRelation):
    
    def __init__(self, source, target, guard=None):
        super().__init__(RelationType.S, source, target, guard)
        self.__spawned = 0
    
    @property
    def spawned(self) -> int:
        return self.__spawned
    
    @spawned.setter
    def spawned(self, value: int):
        self.__spawned = value


class DcrGraph:
    
    def __init__(self, id, template=None):
        self.__id = id
        self.__events = set() if template is None else template.events
        self.__elements = set() if template is None else template.elements
        self.__activityMap = {} if template is None else template.labelMapping
        self.__relations = set() if template is None else template.relations

    @property
    def ID(self) -> str:
        return self.__id
    
    @ID.setter
    def ID(self, value: str):
        self.__id = value

    @property
    def events(self) -> Set[str]:
        return self.__events

    @events.setter
    def events(self, value: Set[str]):
        self.__events = value

    @property
    def elements(self) -> Set[DcrElement]:
        return self.__elements

    @elements.setter
    def labels(self, value: Set[DcrElement]):
        self.__elements = value

    @property
    def activity_map(self) -> Dict[str, DcrActivity]:
        return self.__activityMap

    @activity_map.setter
    def activity_map(self, value: Dict[str, DcrActivity]):
        self.__activityMap = value

    @property
    def relations(self) -> Set[DcrRelation]:
        return self.__relations
    
    @relations.setter
    def relations(self, value: Set[DcrRelation]):
        self.__relations = value

    def getParents(self, element: DcrElement) -> Set[DcrNesting | DcrSubprocess]:
        parents = set()
        for e in self.elements:
            if element in e.children:
                parents.add(e)
        return parents
    
    def hasAsParent(self, child: DcrElement, element: DcrElement) -> bool:
        parents = self.getParents(child)
        if element in parents:
            return True
        else:
            res = False
            for parent in parents:
                res = res or self.hasAsParent(parent, element)
            return res
    
    def initiateSpawnContainers(self, element: DcrElement, subgraph: DcrSubgraph):
        container = DcrSpawnContainer(element.ID + "Container", {element})
        self.elements.add(container)
        for r in self.relations:
            if r.source == element and (not self.hasAsParent(r.target, subgraph) or r.target.):
                r.source = container
            if r.target == element and not self.hasAsParent(r.source, subgraph):
                r.target = container
    # What about internal relations? How to show if a relation is to internal element or of said element?
    # What about graphs with initial instantiations? 
                
        if isinstance(element, DcrNesting | DcrSubprocess) and not isinstance(element, DcrSubgraph):
            for child in element.children:
                self.initiateSpawnContainers(child, subgraph)

    ### Suppose an element has two parents, a subprocess and a nesting. However, the nesting also has the same subprocess as a parent
    ### does this count as the element having two subprocess parents?
    ### If not, make subprocess a set instead and check its length in initiateGraph
    def getNumSubprocessParents(self, element: DcrElement):
        subprocesses = 0
        parents = self.getParents(element)
        for parent in parents:
            if isinstance(parent, DcrSubprocess):
                subprocesses += 1
            else:
                subprocesses += self.getNumSubprocessParents(parent)
        return subprocesses

    def initiateGraph(self):
        for element in self.elements:
            if self.getNumSubprocessParents(element) > 1:
                raise Exception("Element with ID {} is part of more than one subprocess".format(element.ID))

            if isinstance(element, DcrSubgraph):
                for child in element.children:
                    self.initiateSpawnContainers(child, element)
            

    def getEventID(self, activity: DcrActivity) -> str:
        for eventID, dcrActivity in self.activity_map.items():
            if activity == dcrActivity:
                return eventID

    def getActivity(self, eventID: str) -> DcrActivity:
        return self.activity_map[eventID]
    
    def getActivityFromID(self, ID: str) -> DcrActivity:
        for e in self.elements:
            if e.ID == ID:
                return e
        return None

    def getConstraints(self) -> int:
        return len(self.__relations)


    """
    def __repr__(self):
        string = ""
        for key, value in vars(self).items():
            string += str(key.split("_")[-1]) + ": " + str(value) + "\n"
        return string    

    def __str__(self):
        return self.__repr__()

    def __eq__(self, other):
        return self.conditions == other.conditions and self.responses == other.responses and self.includes == other.includes and self.excludes == other.excludes

    def __lt__(self, other):
        return str(self.obj) < str(other.obj)

    def __getitem__(self, item):
        for key, value in vars(self).items():
            if item == key.split("_")[-1]:
                return value
        return set()

    def __setitem__(self, item, value):
        for key,_ in vars(self).items():
            if item == key.split("_")[-1]:
                setattr(self, key, value)
    """