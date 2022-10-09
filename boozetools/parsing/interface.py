"""
Parsing Interface Definitions
"""

END_OF_TOKENS = '<END>' # An agreed artificial "end-of-text" terminal-symbol.
ERROR_SYMBOL = '$error$' # An agreed "error" symbol.
# Note that the scanner should NEVER emit either of the above two symbols.
# However, the error symbol may appear in the right-hand side of a production rule.

class ParseError(ValueError):
	pass
	
class UnexpectedTokenError(ParseError):
	def __init__(self, kind, semantic, pds):
		self.kind = kind
		self.semantic = semantic
		self.pds = pds
	
class UnexpectedEndOfTextError(ParseError):
	def __init__(self, pds):
		self.pds = pds

class ParseErrorListener:
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
		raise UnexpectedTokenError(kind, semantic, pds)
	
	def unexpected_eof(self, pds):
		"""
		The parser ran out of tokens unexpectedly.
		`pds` is the state of the push-down automaton at the point of error.
		"""
		raise UnexpectedEndOfTextError(pds)
	
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
		raise ParseError()
	
	def cannot_recover(self):
		"""
		The parser attempted to enter recovery mode, but there are no
		recoverable states on the parse stack, so recovery is impossible.
		
		Default behavior is `return self.did_not_recover()`
		"""
		return self.did_not_recover()
	
	def exception_parsing(self, ex:Exception, message, args):
		"""
		Q: If a combining function raises an exception, what should happen?
		A: It depends.
		
		Maybe the exception should not happen: some extra context might help
		you reproduce and debug the problem. Log the context and re-raise.
		
		Maybe certain exceptions represent non-fatal conditions, but you'd
		rather separate policy from mechanism. Deal with it and return the
		semantic value that should replace the aborted attribute-synthesis.
		"""
		raise ex from None # Hide the catch-and-rethrow from the traceback.

class HandleFindingAutomaton:
	"""
	This interface captures the operations needed to perform table-driven parsing, as well as a modicum
	of reasonable error reporting. Again, no particular structure or organization is implied.
	"""
	
	# The first several methods are involved in actually finding handles.
	def get_initial(self, language) -> int: raise NotImplementedError(type(self), 'return the initial state id for the selected language, which by the way is usually `None `.')
	def get_translation(self, symbol) -> int: raise NotImplementedError(type(self, 'Because scanners should not care the order of terminals in the parse table. Zero is reserved for end-of-text.'))
	def get_action(self, state_id:int, terminal_id) -> int: raise NotImplementedError(type(self), 'Positive -> successor state id. Negative -> rule id for reduction. Zero -> error.')
	def get_goto(self, state_id:int, nonterminal_id) -> int: raise NotImplementedError(type(self, 'return a successor state id.'))
	def get_breadcrumb(self, state_id:int) -> str: raise NotImplementedError(type(self), 'This is used in error reporting. Return the name of the symbol that shifts into this state.')
	def interactive_step(self, state_id:int) -> int: raise NotImplementedError(type(self), 'Return the reduce instruction for interactive-reducing states; zero otherwise.')

	# The next few are involved in reducing handles. (Yes, this interface is therefore overgrown.)
	def get_rule(self, rule_id:int) -> tuple: raise NotImplementedError(type(self), 'return a (nonterminal_id, length, constructor_id, view) quad.')
	def get_constructor(self, constructor_id) -> object: raise NotImplementedError(type(self), 'return whatever will make sense to the corresponding combiner.')
	def each_constructor(self) : raise NotImplementedError(type(self), "Involved in binding parser tables to drivers. Yield pairs of <constructor, set of mentions>.")
	
	# These next two methods are in support of GLR parsing:
	def get_split_offset(self) -> int: raise NotImplementedError(type(self), "Action entries >= this number mean to split the parser.")
	def get_split(self, split_id:int) -> list: raise NotImplementedError(type(self), "A list of parse actions of the usual (deterministic) form.")


class AbstractParser:
	"""
	Before I get too deep into it, let's lay out the general structure of a generalized parse:
	"""
	def __init__(self, table: HandleFindingAutomaton, combine, language=None):
		""" Please note this takes a driver not a combiner: it does its own selection of arguments from the stack. """
		self._table = table
		self._combine = combine
		self._nr_states = table.get_split_offset()
		self.reset(table.get_initial(language))
	
	def reset(self, initial_state):
		""" Configure the initial stack situation for the given initial automaton state. """
		raise NotImplementedError(type(self))
	
	def consume(self, terminal, semantic):
		""" Call this from your scanning loop. """
		raise NotImplementedError(type(self))

	def finish(self) -> list:
		"""
		Call this after the last token to wrap up and
		:return: a valid semantic value for the parse.
		"""
		raise NotImplementedError(type(self))
