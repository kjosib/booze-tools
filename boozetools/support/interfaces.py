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

END_OF_TOKENS = '<END>' # An agreed artificial "end-of-text" terminal-symbol.
ERROR_SYMBOL = '$error$' # An agreed "error" symbol.
# Note that the scanner should NEVER emit either of the above two symbols.
# However, the error symbol may appear in the right-hand side of a production rule.

class LanguageError(ValueError):
	""" Base class of all exceptions arising from the language machinery. """

class ScannerBlocked(LanguageError):
	"""
	Raised (by default) if a scanner gets blocked.
	Parameters are:
		the string offset where it happened.
		the current start-condition of the scanner.
	"""
	def __init__(self, position, condition):
		super().__init__(position, condition)
		self.position, self.condition = position, condition

# class ParseError(LanguageError):
# 	""" Raised if the parser gets lost trying to reconstruct the structure of a phrase. """
# 	# TODO: Deprecation in progress...
# 	def __init__(self, stack_symbols, lookahead, yylval):
# 		super().__init__(stack_symbols, lookahead, yylval)
# 		self.stack_symbols, self.lookahead, self.yylval = stack_symbols, lookahead, yylval
# 	def condition(self) -> str:
# 		return ' '.join(self.stack_symbols) + ' %s %s'%(pretty.DOT, self.lookahead)
#
class GeneralizedParseError(LanguageError): pass

class DriverError(Exception):
	"""
	This is an exception wrapper around any exception NOT deriving from LanguageError
	which may be raised in the process of trying to invoke a parse action or scan action.

	In order to see the ACTUAL problem at the BOTTOM of the stack trace (and hide all the
	stack frames involved in the bowels of the parse engine), do something like:

	parse = runtime.the_simple_case(tables(), driver, driver, interactive=True)
	try: goal = parse(text.content)
	except interfaces.DriverError as e:
		text.complain(*parse.scanner.current_span(), message=str(e.args))
		raise e.__cause__ from None
	except interfaces.ScannerBlocked as e:
		... complain about a scan error ...
	except interfaces.ParseError as e:
		... complain about a parse error ...

	Maybe code like this will eventually become a convenience method...
	"""

class ErrorChannel:
	"""
	Implement this interface to report/respond to parse errors.
	For the moment I'm assuming you have a handle to the scanner so you
	can get the input-file location of error events...
	"""
	def unexpected_token(self, kind, semantic, pds):
		"""
		The parser has just been given a bogus token.
		It will enter recovery mode next.
		`kind` and `semantic` are whatever the scanner provided.
		`pds` is the state of the push-down automaton at the point of error.
		"""
	
	def unexpected_eof(self, pds):
		"""
		The parser ran out of tokens unexpectedly.
		`pds` is the state of the push-down automaton at the point of error.
		"""
	
	def will_recover(self, tokens):
		"""
		The parser has seen a token sequence sufficient to resynchronize.
		`tokens` is that sequence. The parser will next commit to this
		recovery. (Perhaps there should be a way to prevent it?)
		The return value from this method will appear as the semantic content
		of the "error" position in the error rule that was ultimately chosen.
		"""
	
	def did_not_recover(self):
		"""
		The parser ran out of tokens while in error-recovery mode, and was
		unable to recover.
		"""
	
	def cannot_recover(self):
		"""
		The parser attempted to enter recovery mode, but there are no
		recoverable states on the parse stack, so recovery is impossible.
		"""
	
	def scan_exception(self, e:Exception):
		"""
		Exception `e` bubbled out of the scanner.
		The parser is prepared to try again to read a token.
		"""
		raise e
	
	def rule_exception(self, e:Exception, message, args):
		"""
		Exception `e` bubbled out of the combining function.
		Maybe you'd like to add some context?
		"""
		raise e

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
	def get_rule(self, rule_id:int) -> tuple: raise NotImplementedError(type(self), 'return a (nonterminal_id, length, constructor_id, view) quad.')
	def get_constructor(self, constructor_id) -> object: raise NotImplementedError(type(self), 'return whatever will make sense to the corresponding combiner.')
	def get_initial(self, language) -> int: raise NotImplementedError(type(self), 'return the initial state id for the selected language, which by the way is usually `None `.')
	def get_breadcrumb(self, state_id:int) -> str: raise NotImplementedError(type(self), 'This is used in error reporting. Return the name of the symbol that shifts into this state.')
	def interactive_step(self, state_id:int) -> int: raise NotImplementedError(type(self), 'Return the reduce instruction for interactive-reducing states; zero otherwise.')
	# These next two methods are in support of GLR parsing:
	def get_split_offset(self) -> int: raise NotImplementedError(type(self), "Action entries >= this number mean to split the parser.")
	def get_split(self, split_id:int) -> list: raise NotImplementedError(type(self), "A list of parse actions of the usual (deterministic) form.")
	
class Scanner:
	"""
	This is the interface a scanner action can expect to be able to operate on.
	
	As a convenience, scan-context stack operations are provided here. There is no "reject" action,
	but a powerful and fast alternative is built into the DFA generator in the form of rule priority
	ranks. The longest-match heuristic breaks ties among the highest ranked rules that match.
	"""
	
	def token(self, kind, semantic=None):
		""" Inform the system that a token of whatever kind and semantic is recognized from the current focus. """
		raise NotImplementedError(type(self))
	
	def enter(self, condition):
		""" Enter the scan condition named by parameter `condition`. """
		raise NotImplementedError(type(self))
	def push(self, condition):
		""" Save the current scan condition to a stack, and enter the scan state named by parameter `condition`. """
		raise NotImplementedError(type(self))
	def pop(self):
		""" Enter the scan condition popped from the top of the stack. """
		raise NotImplementedError(type(self))
	def matched_text(self) -> str:
		""" Return the text currently matched. """
		raise NotImplementedError(type(self))
	def less(self, nr_chars:int):
		""" Put back characters into the stream to be matched: This also provides the mechanism for fixed trailing context. """
		raise NotImplementedError(type(self))
	def current_position(self) -> int:
		""" As advertised. This was motivated by a desire to produce helpful error messages. """
		raise NotImplementedError(type(self))
	def current_span(self):
		""" Return the position and length of the current match-text for use in error-reporting calls and the like. """
		raise NotImplementedError(type(self))
	def current_condition(self) -> str:
		""" Return the most recently entered (or pushed, or popped) start-condition name, which is super-helpful debugging scanners. """
		raise NotImplementedError(type(self))

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
	
	def invoke(self, yy:Scanner, rule_id:int) -> object:
		"""
		Override this according to your application.
		The generic scanner algorithm will yield any non-null return values from this function.
		"""
		raise NotImplementedError(type(self), ScanRules.invoke.__doc__)

	def blocked(self, yy:Scanner):
		"""
		The scanner will call this to report blockage. It will have prepared
		to skip the offending character. Your job is to report the error to
		the user. Try to recover. Emit a designated "nonsense" token and let
		the parser handle it. Delegate to a driver. Do whatever.
		
		Default behavior is to raise an exception, which by the way will kill
		off a parse(...) in progress -- at least until I get parse error
		recovery mode finished.
		"""
		raise ScannerBlocked(yy.current_position(), yy.current_condition())

