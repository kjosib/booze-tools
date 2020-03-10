"""
This module implements the essential algorithm to recognize a sequence of
lexemes and their syntactic categories (rules/scan-actions) by reference to a
finite-state machine. It supports backtracking, beginning-of-line anchors,
and (non-variable) trailing context.
"""

from ..support import interfaces


class IterableScanner(interfaces.Scanner):
	"""
	This is the standard generic finite-automaton-based scanner, with support for backtracking,
	beginning-of-line anchors, and (non-variable) trailing context.
	
	Your application must provide a suitable finite-automaton, rule bindings, and error handler.
	"""
	def __init__(self, *, text:str, automaton: interfaces.FiniteAutomaton, rules: interfaces.ScanRules, start):
		if not isinstance(text, str): raise ValueError('text argument should be a string, not a ', type(text))
		self.__text = text
		self.__automaton = automaton
		self.__rules = rules
		self.enter(start)
		self.__stack = []
		self.__start, self.__mark = None, None
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
	
	def matched_text(self) -> str:
		""" As advertised. """
		return self.__text[self.__start:self.__mark]
	
	def less(self, nr_chars:int):
		"""
		Put trailing characters back into the stream to be matched.
		This is also the mechanism for trailing context.
		if `nr_chars` is zero or positive, the current match is adjusted to
		consume precisely that many characters. If it's negative, then a
		corresponding number of characters are dropped from the end of the
		match, and these will be considered again in the next matching cycle.
		"""
		new_mark = (self.__mark if nr_chars < 0 else self.__start) + nr_chars
		assert self.__start <= new_mark <= self.__mark
		self.__mark = new_mark
	
	def scan_one_raw_lexeme(self, q) -> int:
		"""
		This is how the magic happens. Given a starting state, this algorithm finds the
		end of the lexeme to be matched and the rule number (if any) that applies to the match.
		
		This algorithm deliberately ignores a zero-width, zero-context match, but it may fail
		to consume any characters (returning None). The caller must deal properly with that case.
		"""
		text, automaton = self.__text, self.__automaton
		cursor, mark, rule_id, jam = self.__start, self.__start, None, automaton.jam_state()
		while True:
			try: codepoint = ord(text[cursor])
			except IndexError: codepoint = -1 # EAFP: Python will check string length anyway...
			q = automaton.get_next_state(q, codepoint)
			if q == jam: break
			cursor += 1
			q_rule = automaton.get_state_rule_id(q)
			if q_rule is not None: mark, rule_id = cursor, q_rule
		self.__mark = mark
		return rule_id
	
	def __q0(self):
		""" Return the current "initial" state of the automaton, based on condition and context. """
		at_begin_line = self.__start == 0 or self.__text[self.__start - 1] in '\r\n'
		return self.__condition[at_begin_line]
	
	def token(self, kind, semantic=None):
		""" Be it established, then, that the token stream shall consist of... """
		assert kind is not None
		self.__buffer.append((kind, semantic, self.__start, self.__mark))
	
	def __iter__(self):
		text, automaton, rules = self.__text, self.__automaton, self.__rules
		self.__start, eot = 0, len(text)
		while self.__start < eot:
			rule_id = self.scan_one_raw_lexeme(self.__q0())
			if rule_id is None:
				self.__mark = self.__start + 1 # generally we shall skip the offending character...
				rules.blocked(self) # and let the rules driver have a crack at doing something better.
			else:
				trail = rules.get_trailing_context(rule_id)
				if trail is not None: self.less(trail)
				rules.invoke(self, rule_id)
			yield from self.__buffer
			self.__buffer.clear()
			self.__start = self.__mark
		# Now determine if an end-of-file rule needs to execute:
		q = automaton.get_next_state(self.__q0(), -1)
		if q>=0:
			rules.invoke(self, automaton.get_state_rule_id(q))
			yield from self.__buffer
			self.__buffer.clear()
		
	def current_position(self) -> int:
		""" As advertised. This was motivated by a desire to produce helpful error messages. """
		return self.__start
	def current_span(self):
		""" Return the position and length of the current match-text for use in error-reporting calls and the like. """
		return self.__start, self.__mark - self.__start