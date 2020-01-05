"""
This module implements the essential algorithm to recognize a sequence of lexemes and
their syntactic categories (rules/scan-actions) by reference to a finite-state machine.
"""

from ..support import interfaces


class Scanner(interfaces.ScanState):
	"""
	This is the standard generic finite-automaton-based scanner, with support for backtracking,
	beginning-of-line anchors, and (non-variable) trailing context.
	
	Your application is expected to provide a suitable finite-automaton and rule bindings.
	
	This object can participate in Python's iterator-protocol: Whatever the rule-bindings return
	from their .invoke(...) method, the iterator yields (except `None`).
	
	The scanner-as-iterator idea is reasonably efficient and usually convenient, but it comes
	with a weakness: if more than one token comes out of a single scan match (as is the case for
	indent-grammars) then you will want a different approach.
	"""
	def __init__(self, *, text:str, automaton: interfaces.FiniteAutomaton, rules: interfaces.ScanRules, start):
		if not isinstance(text, str): raise ValueError('text argument should be a string, not a ', type(text))
		self.__text = text
		self.__automaton = automaton
		self.__rules = rules
		self.enter(start)
		self.__stack = []
		self.__start, self.__mark = None, None
	
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
		""" Put back characters into the stream to be matched: This also provides the mechanism for fixed trailing context. """
		# NB: Zero only makes any sense for fixed-length trailing context if it means no trailing context.
		# NB: The present code is somewhat of a hack because "is None" may be faster than "==0" in Python.
		# NB: It also allows for an empty stem, which cannot presently be specified but may be useful.
		# NB: Support for variable-stem-variable-trail patterns requires more than an integer anyway.
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
		
	def __iter__(self):
		text, automaton, rules = self.__text, self.__automaton, self.__rules
		self.__start, eot = 0, len(text)
		while self.__start < eot:
			rule_id = self.scan_one_raw_lexeme(self.__q0())
			if rule_id is None:
				self.__mark = self.__start + 1
				token = rules.unmatched(self, text[self.__start])
			else:
				trail = rules.get_trailing_context(rule_id)
				if trail is not None: self.less(trail)
				token = rules.invoke(self, rule_id)
			if token is not None: yield token
			self.__start = self.__mark
		# Now determine if an end-of-file rule needs to execute:
		q = automaton.get_next_state(self.__q0(), -1)
		if q>=0:
			token = rules.invoke(self, automaton.get_state_rule_id(q))
			if token is not None: yield token
		
	def current_position(self) -> int:
		""" As advertised. This was motivated by a desire to produce helpful error messages. """
		return self.__start
	def current_span(self):
		""" Return the position and length of the current match-text for use in error-reporting calls and the like. """
		return self.__start, self.__mark - self.__start