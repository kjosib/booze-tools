"""
"""
from .interface import INITIAL, END_OF_INPUT, FiniteAutomaton, Bindings, RuleId

def _make_reader(subject):
	if isinstance(subject, str):
		return lambda offset: ord(subject[offset])
	elif isinstance(subject, (bytes, bytearray)):
		return subject.__getitem__
	else:
		raise TypeError()

def scan_one_raw_lexeme(fa:FiniteAutomaton, codepoint_at, cursor, condition:str) -> tuple[int, RuleId]:
	"""
	This is how the magic happens. Given a start-condition, this algorithm finds the
	end of the lexeme to be matched and the rule number (if any) that applies to the match.
	This algorithm deliberately ignores a zero-width, zero-context match, but it may fail
	to consume any characters. The caller must deal properly with that case.
	"""
	right, rule_id, jammed = cursor, None, fa.jam_state()
	is_at_start_of_line = cursor == 0 or codepoint_at(cursor - 1) in {10, 13}
	state = fa.condition(condition)[is_at_start_of_line]
	while True:
		try: codepoint = codepoint_at(cursor)
		except IndexError: codepoint = END_OF_INPUT
		state = fa.transition(state, codepoint)
		if state == jammed: break
		cursor += 1
		accept = fa.accept(state)
		if accept is not None:
			right, rule_id = cursor, accept
	return right, rule_id

class Scanner:
	"""
	This is the standard generic finite-automaton-based scanner, with support for backtracking,
	beginning-of-line anchors, and (non-variable) trailing context.
	"""
	
	condition : str
	
	def __init__(self, text, fa:FiniteAutomaton, bindings:Bindings, start=INITIAL, at=0):
		self.__text = text
		self.__size = len(text)
		self.__read = _make_reader(text)
		self.__fa = fa
		self.__bindings = bindings
		self.__stack = []
		self.enter(start)
		self.left = self.right = at
		
	def scan_one_item(self):
		cursor = self.left = self.right
		self.right, rule_id = scan_one_raw_lexeme(self.__fa, self.__read, cursor, self.condition)
		if rule_id is None:
			self.right = cursor + 1
			self.__bindings.on_stuck(self)
		else:
			self.__bindings.on_match(self, rule_id)
	
	def scan_repeatedly(self):
		while self.has_more():
			self.scan_one_item()
	
	def has_more(self):
		return self.right < self.__size
	
	def enter(self, condition):
		""" Change to a different start-condition. """
		self.condition = condition
	def push(self, condition):
		""" Push the current start-condition onto a stack and change to the one specified. """
		self.__stack.append(self.condition)
		self.enter(condition)
	def pop(self):
		""" Jump back to a start-condition pulled from the condition stack. """
		self.enter(self.__stack.pop())
		
	def slice(self):
		""" Return a slice-object corresponding to the extent of matched text. """
		return slice(self.left, self.right)
	def match(self):
		""" Return the actual matched text """
		return self.__text[self.left:self.right]

	def less(self, nr_chars):
		"""
		Put trailing characters back into the stream to be matched.
		This is also the mechanism for trailing context.
		if `nr_chars` is zero or positive, the current match is adjusted to
		consume precisely that many characters. If it's negative, then a
		corresponding number of characters are dropped from the end of the
		match, and these will be considered again in the next matching cycle.
		(If `nr_chars` is None, nothing happens.)
		"""
		if nr_chars is not None:
			self.right = (self.right if nr_chars < 0 else self.left) + nr_chars
	def seek(self, position):
		""" Scanning will next resume at the position given. """
		self.right = position

class IterableScanner(Scanner):
	"""
	It may be convenient that iterating over a scanner would cause it to yield tokens.
	Scan-actions can call yy.token(...) and this object wraps that into an iterable.
	"""
	
	def __init__(self, text, fa: FiniteAutomaton, bindings: Bindings, start=INITIAL, at=0):
		super().__init__(text, fa, bindings, start, at)
		self.__buffer = []
	
	def __iter__(self):
		while self.has_more():
			self.scan_one_item()
			yield from self.__buffer
			self.__buffer.clear()
	
	def token(self, kind: str, semantic=None):
		"""
		During scan rule invocation, call this method with tokens for the
		scanner to yield once it gets control back. For integration with
		the parsing mechanism, a token is defined as a 2-tuple consisting
		of "kind" and arbitrary/optional semantic value.
		"""
		assert kind is not None
		self.__buffer.append((kind, semantic))
