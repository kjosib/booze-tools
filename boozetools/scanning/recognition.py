"""
This module implements the essential algorithm to recognize a sequence of
lexemes and their syntactic categories (rules/scan-actions) by reference to a
finite-state machine. It supports backtracking, beginning-of-line anchors,
and (non-variable) trailing context.
"""
from typing import TypeVar, Generic
from ..support import interfaces

T = TypeVar('T')

END_OF_INPUT = -1 # Used in place of a character ordinal. Agrees with the DFA builder.


class CursorBase(Generic[T]):
	"""
	I extracted this bit out of the scanner implementation for three reasons:
		1. Scanning strings and bytes-objects requires slightly different access syntax.
		2. Now the scanner and other code can take turns consuming interleaved input.
		3. It opens a path to asynchronous/online scanning, starting before the full input arrives.
	"""

	left: int
	right: int

	_subject: T
	_size:int

	def __init__(self, subject:T, offset:int=0):
		self._subject = subject
		self._size = len(self._subject)
		self.left = self.right = offset
	def codepoint_at(self, offset) -> int: raise NotImplementedError(type(self))
	def selected_portion(self) -> T: return self._subject[self.left:self.right]
	def finish(self): self.left = self.right
	def is_at_start_of_line(self) -> bool:
		return self.left == 0 or self.codepoint_at(self.left - 1) in (10, 13)
	def is_exhausted(self) -> bool:
		return self.left >= self._size

class StringCursor(CursorBase[str]):
	def codepoint_at(self, offset) -> int: return ord(self._subject[offset])

class BytesCursor(CursorBase[bytes]):
	def codepoint_at(self, offset) -> int: return self._subject[offset]



class IterableScanner(interfaces.Scanner):
	"""
	This is the standard generic finite-automaton-based scanner, with support for backtracking,
	beginning-of-line anchors, and (non-variable) trailing context.
	
	Your application must provide a suitable finite-automaton, rule bindings, and error handler.

	It seems convenient that iterating over the scanner should cause it to yield tokens.
	This is certainly not the only reasonable approach: we could instead explicitly
	call a method expecting to get a token back. However, this creates a synchronization
	hassle: some scan rules emit no tokens, while others may emit more than one.
	Fortunately, Python generators solve the problem: if you want the "call for tokens"
	metaphor, then the `iter()` and `next()` built-in functions give you that.
	"""
	def __init__(self, *, text, automaton: interfaces.FiniteAutomaton, rules: interfaces.ScanRules, start, on_error:interfaces.ScanErrorListener):
		if isinstance(text, str): text = StringCursor(text)
		elif isinstance(text, bytes): text = BytesCursor(text)
		assert isinstance(text, CursorBase), type(text)
		self.cursor = text
		self.__automaton = automaton
		self.__rules = rules
		self.on_error = on_error
		self.enter(start)
		self.__stack = []
		self.__buffer = []
	
	def enter(self, condition):
		self.__condition_name = condition
		self.__condition = self.__automaton.get_condition(condition)
		
	def pop(self):
		self.enter(self.__stack.pop())
		
	def push(self, condition):
		self.__stack.append(self.__condition_name)
		self.enter(condition)
		
	def current_condition(self):
		return self.__condition_name
	
	def matched_text(self):
		""" As advertised. """
		return self.cursor.selected_portion()

	def less(self, nr_chars:int):
		"""
		Put trailing characters back into the stream to be matched.
		This is also the mechanism for trailing context.
		if `nr_chars` is zero or positive, the current match is adjusted to
		consume precisely that many characters. If it's negative, then a
		corresponding number of characters are dropped from the end of the
		match, and these will be considered again in the next matching cycle.
		"""
		cursor = self.cursor
		mark = (cursor.right if nr_chars < 0 else cursor.left) + nr_chars
		assert cursor.left <= mark <= cursor.right
		cursor.right = mark
	
	def scan_one_raw_lexeme(self, q) -> int:
		"""
		This is how the magic happens. Given a starting state, this algorithm finds the
		end of the lexeme to be matched and the rule number (if any) that applies to the match.
		
		This algorithm deliberately ignores a zero-width, zero-context match, but it may fail
		to consume any characters (returning None). The caller must deal properly with that case.
		"""
		cursor = self.cursor
		automaton = self.__automaton
		position, mark, rule_id, jam = cursor.left, cursor.left, None, automaton.jam_state()
		while True:
			try: codepoint = cursor.codepoint_at(position)
			except IndexError: codepoint = END_OF_INPUT # EAFP: Python will check string length anyway...
			q = automaton.get_next_state(q, codepoint)
			if q == jam: break
			position += 1
			q_rule = automaton.get_state_rule_id(q)
			if q_rule is not None: mark, rule_id = position, q_rule
		cursor.right = mark
		return rule_id
	
	def token(self, kind:str, semantic=None):
		"""
		During scan rule invocation, call this method with tokens for the
		scanner to yield once it gets control back. For integration with
		the parsing mechanism, a token is defined as a 2-tuple consisting
		of "kind" and arbitrary/optional semantic value.
		"""
		assert kind is not None
		self.__buffer.append((kind, semantic))
	
	def __iter__(self):
		"""
		It seems convenient that iterating over the scanner should cause it to scan...
		"""
		
		def fire_rule(rule_id):
			if rule_id is None:
				cursor.right = cursor.left + 1 # Prepare to "match" the offending character...
				self.on_error.unexpected_character(self) # and delegate to the error handler, which may do anything.
			else:
				trail = rules.get_trailing_context(rule_id)
				if trail is not None: self.less(trail)
				try: rules.invoke(self, rule_id)
				except Exception as ex: self.on_error.exception_scanning(self, rule_id, ex)
				yield from self.__buffer
				self.__buffer.clear()

		def q0():
			""" Return the current "initial" state of the automaton, based on condition and context. """
			return self.__condition[cursor.is_at_start_of_line()]

		cursor, automaton, rules = self.cursor, self.__automaton, self.__rules
		while not cursor.is_exhausted():
			yield from fire_rule(self.scan_one_raw_lexeme(q0()))
			cursor.finish()
		# Now determine if an end-of-file rule needs to execute:
		q = automaton.get_next_state(q0(), END_OF_INPUT)
		if q>=0: yield from fire_rule(automaton.get_state_rule_id(q))
		
	def current_position(self) -> int:
		""" As advertised. This was motivated by a desire to produce helpful error messages. """
		return self.cursor.left
	def current_span(self):
		""" Return the position and length of the current match-text for use in error-reporting calls and the like. """
		return self.cursor.left, self.cursor.right - self.cursor.left