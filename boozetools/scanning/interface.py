"""
Scanning Interface Definitions.
"""
from abc import ABC, abstractmethod
from typing import TypeVar, NamedTuple, Optional, Any

State = TypeVar("State")
Symbol = int
RuleId = int

CodePoint = int
ConditionVector = tuple[State, State]

INITIAL = 'INITIAL'
END_OF_INPUT : CodePoint = -1

class ScannerBlocked(ValueError):
	"""
	Raised (by default) if a scanner gets blocked.
	Parameters are:
		the string offset where it happened.
		the current start-condition of the scanner.
	"""
	def __init__(self, position, condition):
		super().__init__(position, condition)
		self.position, self.condition = position, condition
		
		
class FiniteAutomaton(ABC):
	"""
	A finite automaton determines which rule matches but knows nothing about the rules themselves.
	This interface captures the operations required to execute the general scanning algorithm.
	It is deliberately decoupled from any particular representation of the underlying data.
	"""
	
	@abstractmethod
	def jam_state(self):
		""" DFA might provide -1, while NFA might provide an empty frozenset(). """

	@abstractmethod
	def condition(self, name:str) -> ConditionVector:
		""" A "condition" is (currently) a pair of state_ids for the normal and beginning-of-line cases. """
	
	@abstractmethod
	def transition(self, state: State, codepoint: CodePoint) -> State:
		""" The FSM's delta function. """
	
	@abstractmethod
	def accept(self, state: State) -> RuleId:
		""" Return the associated rule ID if this state is terminal, otherwise None. """
	
	
class Classifier(ABC):
	"""
	Normally a finite-state automaton (FA) based scanner does not represent all possible input
	characters as individual and distinct. Rather, all possible characters are mapped
	to a much smaller alphabet of symbols which are distinguishable from their neighbors
	in terms of their effect on the operation of the FA.
	It is this object's responsibility to perform that mapping via method `classify`.
	"""
	
	@abstractmethod
	def classify(self, codepoint: CodePoint) -> Symbol:
		"""
		Map a unicode codepoint to a specific numbered character class
		such that 0 <= result < self.cardinality()
		as known to a corresponding finite automaton.
		"""
	
	@abstractmethod
	def cardinality(self) -> int:
		""" Return the number of distinct classes which may be emitted by self.classify(...). """
	
	@abstractmethod
	def display(self):
		""" Pretty-print a suitable representation of the innards of this classifier's data. """

class Bindings(ABC):
	
	@abstractmethod
	def on_match(self, yy, rule_id:RuleId):
		""" Delegate. If there's right-context, call yy.less(amount) to implement it before delegating. """
		# act = self.__act[rule_id]
		# self.less(act.right_context)
		# self.__method[rule_id](self, *act.args)
		
	def on_stuck(self, yy):
		""" If you override this to return normally, scanning will continue normally afterward. """
		raise ScannerBlocked(yy.left, yy.condition)
