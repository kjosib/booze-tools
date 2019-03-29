""" The essential algorithms are given in this file. """
from . import interfaces



def parse(tables: interfaces.ParserTables, combine, each_token, *, language=None, interactive=False):
	"""
	The canonical table-driven LR parsing algorithm. As much as possible is left abstract.
	Perhaps unfortunately, there's no explicit support for location tracking here, although
	in some sense that can be left to the tokenizer and the combiner.
	:param tables: The algorithm cares not where they came from or how they are represented.
	:param combine: Responsible to provide the result of a reduction on the attribute stack.
	:param each_token: Iterable source of <terminal, attribute> pairs.
	:param language: Choice of starting language, for multi-language tables.
	:param interactive: Whether the parser should reduce interactively.
	:return: Whatever the last combine(...) call returns as the semantic value of the sentence.
	"""
	state_stack, attribute_stack = [0 if language is None else tables.get_initial(language)], []
	def tos() -> int: return state_stack[-1]
	def reduce(rule_id):
		assert rule_id >= 0
		nonterminal_id, length, message = tables.get_rule(rule_id)
		attribute = attribute_stack[-1] if message is None else combine(message, attribute_stack)
		if length:
			del state_stack[-length:]
			del attribute_stack[-length:]
		state_stack.append(tables.get_goto(tos(), nonterminal_id))
		attribute_stack.append(attribute)
	def prepare_to_shift(terminal_id) -> int:
		while True:
			step = tables.get_action(tos(), terminal_id)
			if step >= 0: break
			reduce(-step-1) # Bison parsers offset the rule data to save a decrement, but that breaks abstraction.
		if step == 0: raise interfaces.ParseError([tables.get_breadcrumb(q) for q in state_stack[1:]], symbol if terminal_id else '<<END>>')
		return step
	for symbol, attribute in each_token:
		state_stack.append(prepare_to_shift(tables.get_translation(symbol)))
		attribute_stack.append(attribute)
		if interactive:
			while True:
				step = tables.interactive_step(tos())
				if step < 0: reduce(-step-1)
				else: break
	prepare_to_shift(0)
	return attribute_stack[0]

class Scanner(interfaces.ScanState):
	"""
	This is the standard generic finite-automaton-based scanner, with support for backtracking,
	beginning-of-line anchors, and (non-variable) trailing context.
	
	Your application is expected to provide a suitable finite-automaton and rulebase, and
	also to override the invoke(...) and perhaps unmatched(...) methods to return whatever tokens
	should come out.
	
	"""
	def __init__(self, *, text:str, automaton: interfaces.FiniteAutomaton, rulebase: interfaces.ScanRules, start):
		if not isinstance(text, str): raise ValueError('text argument should be a string, not a ', type(text))
		self.__text = text
		self.__automaton = automaton
		self.__rulebase = rulebase
		self.__condition = automaton.get_condition(start)
		self.__stack = []
		self.__start, self.__mark, self.__bol = None, None, None
	
	def enter(self, condition): self.__condition = self.__automaton.get_condition(condition)
	def pop(self): self.__condition = self.__stack.pop()
	def push(self, condition):
		self.__stack.append(self.__condition)
		self.enter(condition)
	
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
		self.__bol = new_mark == 0 or self.__text[new_mark-1] in '\r\n'
	def __iter__(self):
		"""
		This algorithm deliberately ignores a zero-width, zero-context match.
		"""
		text, automaton, rulebase = self.__text, self.__automaton, self.__rulebase
		self.__start, eot, self.__bol, jam = 0, len(text), True, automaton.jam_state()
		while self.__start < eot:
			q, cursor, mark, rule_id = self.__condition[self.__bol], self.__start, None, None
			while True:
				q = automaton.get_next_state(q, ord(text[cursor]) if cursor < eot else -1)
				if q == jam: break
				cursor += 1
				q_rule = automaton.get_state_rule_id(q)
				if q_rule is not None: mark, rule_id = cursor, q_rule
			if rule_id is None:
				self.__mark = self.__start + 1
				token = rulebase.unmatched(self, text[self.__start])
			else:
				self.__mark = mark
				trail = rulebase.get_trailing_context(rule_id)
				if trail is None: self.__bol = text[mark-1] in '\r\n'
				else: self.less(trail)
				token = rulebase.invoke(self, rule_id)
			if token is not None: yield token
			self.__start = self.__mark
		# Now determine if an end-of-file rule needs to execute:
		q = automaton.get_next_state(self.__condition[self.__bol], -1)
		if q>=0:
			token = rulebase.invoke(self, automaton.get_state_rule_id(q))
			if token is not None: yield token
	def current_position(self) -> int:
		""" As advertised. This was motivated by a desire to produce helpful error messages. """
		return self.__start