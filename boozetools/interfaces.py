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
	
class ScanRules:
	""" The interface a scan-in-progress needs about trailing context and action selectors. """
	
	def initial_condition(self) -> str:
		""" The default scan condition, which must work for the FiniteAutomaton's .get_condition(...) method. """
		raise NotImplementedError(type(self), ScanRules.initial_condition.__doc__)
	
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
	
	def get_rule_action(self, rule_id:int) -> object:
		"""
		This should return some kind of message that the Scanner subclass will interpret within its .invoke(...) method.
		In a sense, this is therefore a data coupling, in that the two classes need to agree on a data format. However,
		this also means that a single ScanRules object is completely re-entrant: the scan operates in its own context.
		"""
		raise NotImplementedError(type(self), ScanRules.get_rule_action.__doc__)
	

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
	