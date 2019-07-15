"""
This file aggregates various abstract classes and exception types which BoozeTools deals in.

There's a principle of object-oriented design which says "ask not for data, but for help."
At first glance the ADTs for FiniteAutomaton and ParseTable appear to respect that dictum
only by its violation, as suggested by all these `get_foobar` methods. What gives?

Quite a bit, actually: The scanning and parsing algorithms are data-driven, but the essential
nature of those algorithms should not care about the internal structure and organization of that
data, so long as the proper relevant questions may be answered. This provides the flexibility
to plug in different types of compaction (or no compaction at all) without a complete re-write.

A good modular interface exposes abstract data types and the operations among those types.
The methods on FiniteAutomaton and ParseTable are exactly those needed for the interesting
data-driven algorithms they support, without regard to their internal structure.

On a separate note, you could make a good case for splitting this file in twain. Maybe later.
"""

from . import pretty


class LanguageError(ValueError): pass
class ScanError(LanguageError): pass
class ParseError(LanguageError):
	def __init__(self, stack_symbols, lookahead, yylval):
		super(ParseError, self).__init__(stack_symbols, lookahead, yylval)
		self.stack_symbols, self.lookahead, self.yylval = stack_symbols, lookahead, yylval
	def condition(self) -> str:
		return ' '.join(self.stack_symbols) + ' %s %s'%(pretty.DOT, self.lookahead)
class GeneralizedParseError(LanguageError): pass
class SemanticError(LanguageError): pass
class MetaError(LanguageError):
	""" This gets raised if there's something wrong in the definition of a parser or scanner. """
	pass
class PurityError(MetaError):
	""" Raised if a grammar has the wrong/undeclared conflicts. """

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
	

class ParseTable:
	"""
	This interface captures the operations needed to perform table-driven parsing, as well as a modicum
	of reasonable error reporting. Again, no particular structure or organization is implied.
	"""
	def get_translation(self, symbol) -> int: raise NotImplementedError(type(self, 'Because scanners should not care the order of terminals in the parse table. Zero is reserved for end-of-text.'))
	def get_action(self, state_id:int, terminal_id) -> int: raise NotImplementedError(type(self), 'Positive -> successor state id. Negative -> rule id for reduction. Zero -> error.')
	def get_goto(self, state_id:int, nonterminal_id) -> int: raise NotImplementedError(type(self, 'return a successor state id.'))
	def get_rule(self, rule_id:int) -> tuple: raise NotImplementedError(type(self), 'return a (nonterminal_id, length, message) triple.')
	def get_initial(self, language) -> int: raise NotImplementedError(type(self), 'return the initial state id for the selected language.')
	def get_breadcrumb(self, state_id:int) -> str: raise NotImplementedError(type(self), 'This is used in error reporting. Return the name of the symbol that shifts into this state.')
	def interactive_step(self, state_id:int) -> int: raise NotImplementedError(type(self), 'Return the reduce instruction for interactive-reducing states; zero otherwise.')
	# These next two methods are in support of GLR parsing:
	def get_split_offset(self) -> int: raise NotImplementedError(type(self), "Action entries >= this number mean to split the parser.")
	def get_split(self, split_id:int) -> list: raise NotImplementedError(type(self), "A list of parse actions of the usual (deterministic) form.")
	
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
	The interface a scan-in-progress needs about:
		1. trailing context, and
		2. how to invoke scan rules.
	"""
	
	def get_trailing_context(self, rule_id: int):
		"""
		Fixed trailing context is supported: return a negative number of characters to chop
		from the end of the match. Variable trailing context is supported if the leading stem
		has fixed length: return a positive (or zero) number. The absence of trailing context
		should be indicated by returning None.
		
		It's anticipated that a zero-width stem with trailing context might be used to do things
		like decide which scan state to enter and then restart the scanner from the same point.
		
		It would be a reasonable alternative architecture to design the trailing-context
		support as a separate object in a chain-of-responsibility between the scanner and
		driver. The downside is semantic: trailing context is a feature of the scanner-generator
		and as such should be inseparable from the runtime. It might be a cool performance hack
		to leave out trailing-context support when the feature is not used but that's the sort
		of thing that you build into a tool that generates (e.g.) C code from an automaton.
		
		At some later date, I may decide to add support for both variable leading and trailing
		parts of the same rule. That would mean several additional decisions and added complexity,
		which would definitely justify the alternative design mentioned above.
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


	
