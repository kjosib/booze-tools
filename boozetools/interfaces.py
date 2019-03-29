"""
This file aggregates various exception types and abstract classes which you'll deal with when using BoozeTools.
"""

class LanguageError(ValueError): pass
class ScanError(LanguageError): pass
class ParseError(LanguageError): pass
class SemanticError(LanguageError): pass
class MetaError(LanguageError):
	""" This gets raised if there's something wrong in the definition of a parser or scanner. """
	pass

class Classifier:
	"""
	Normally a finite-state automaton (FA) based scanner does not treat all possible input
	characters as individual and distinct. Rather, all possible characters are mapped
	to a much smaller alphabet of symbols which are distinguishable from their neighbors
	in terms of their effect on the operation of the FA.

	It is this object's responsibility to perform that mapping via method `classify`.
	"""
	def classify(self, codepoint:int) -> int:
		"""
		Map a unicode codepoint to a specific numbered character class
		such that 0 <= result < self.cardinality()
		as known to a corresponding finite automaton.
		"""
		raise NotImplementedError(type(self))
	def cardinality(self) -> int:
		""" Return the number of distinct classes which may be emitted by self.classify(...). """
		raise NotImplementedError(type(self))
	def display(self):
		""" Pretty-print a suitable representation of the innards of this classifier's data. """
		raise NotImplementedError(type(self))

class FiniteAutomaton:
	"""
	A finite automaton determines which rule matches but knows nothing about the rules themselves.
	This interface captures the operations required to execute the general scanning algorithm.
	It is deliberately decoupled from any particular representation of the underlying data.
	"""
	def jam_state(self): raise NotImplementedError(type(self)) # DFA might provide -1, while NFA might provide an empty frozenset().

	def get_condition(self, condition_name) -> tuple:
		""" A "condition" is implemented as a pair of state_ids for the normal and begining-of-line cases. """
		raise NotImplementedError(type(self))
	
	def get_next_state(self, current_state: int, codepoint: int) -> int:
		""" Does what it says on the tin. codepoint will be -1 at end-of-file, so be prepared. """
		raise NotImplementedError(type(self))
	
	def get_state_rule_id(self, state_id: int) -> int:
		""" Return the associated rule ID if this state is terminal, otherwise None. """
		raise NotImplementedError(type(self))

	def default_initial_condition(self) -> str:
		"""
		The default scan condition, which must work for the FiniteAutomaton's .get_condition(...) method.
		Moved from ScanRules because it's more strongly coupled to what the FiniteAutomaton knows about.
		"""
		raise NotImplementedError(type(self), FiniteAutomaton.default_initial_condition.__doc__)
	

class ParserTables:
	"""
	This interface captures the operations needed to perform table-driven parsing, as well as a modicum
	of reasonable error reporting. Note that rules begin at 1, because 0 is the error action.
	"""
	def get_translation(self, symbol) -> int: raise NotImplementedError(type(self, 'Because scanners may be oblivious to the order of terminals in the parse table. Zero is reserved for EOT.'))
	def get_action(self, state_id:int, terminal_id) -> int: raise NotImplementedError(type(self))
	def get_goto(self, state_id:int, nonterminal_id) -> int: raise NotImplementedError(type(self, 'return a successor state id.'))
	def get_rule(self, rule_id:int) -> tuple: raise NotImplementedError(type(self), 'return a (nonterminal_id, length, message) triple.')
	def get_initial(self, language) -> int: raise NotImplementedError(type(self), 'return the initial state id for the selected language.')
	def get_breadcrumb(self, state_id:int) -> str: raise NotImplementedError(type(self), 'This is used in error reporting.')
	def interactive_step(self, state_id:int) -> int: raise NotImplementedError(type(self))

class ScanState:
	"""
	This is the interface a scanner action can expect to be able to operate on.
	
	As a convenience, scan-context stack operations are provided here. There is no "reject" action,
	but a powerful and fast alternative is built into the DFA generator in the form of rule priority
	ranks. The longest-match heuristic breaks ties among the highest ranked rules that match.
	"""
	
	def enter(self, condition):
		""" Enter the scan condition named by parameter `condition`. """
		raise NotImplementedError
	def push(self, condition):
		""" Save the current scan condition to a stack, and enter the scan state named by parameter `condition`. """
		raise NotImplementedError
	def pop(self):
		""" Enter the scan condition popped from the top of the stack. """
		raise NotImplementedError
	def matched_text(self) -> str:
		""" Return the text currently matched. """
		raise NotImplementedError
	def less(self, nr_chars:int):
		""" Put back characters into the stream to be matched: This also provides the mechanism for fixed trailing context. """
		raise NotImplementedError
	def current_position(self) -> int:
		""" As advertised. This was motivated by a desire to produce helpful error messages. """

class ScanRules:
	"""
	The interface a scan-in-progress needs about trailing context and how to invoke scan rules.
	"""
	
	def get_trailing_context(self, rule_id: int):
		"""
		Fixed trailing context is supported: return a negative number of characters to chop from the end of the match.
		Variable trailing context is supported if the leading stem has fixed length: return a positive (or zero) number.
		The absence of trailing context should be indicated by returning None.

		It's anticipated that a zero-width stem with trailing context might be used to decide which scan state to enter.
		At some later date, I may decide to add support for variable leading and trailing portions, but this would
		require some changes to the scanning algorithm. It COULD be a matter of this method returning a sentinel
		and then another method returning information sufficient to identify the boundary between stem and trail.
		"""
		raise NotImplementedError(type(self), ScanRules.get_trailing_context.__doc__)
	
	def unmatched(self, state:ScanState, char):
		""" By default, this raises an exception. You may wish to override it in your application. """
		raise ScanError(state.current_position(), char)
	
	def invoke(self, scan_state:ScanState, rule_id:int) -> object:
		"""
		Override this according to your application.
		The generic scanner algorithm will yield any non-null return values from this function.
		"""
		raise NotImplementedError(type(self), ScanRules.invoke.__doc__)


	
