""" The essential algorithms are given in this file. """
from . import interfaces


def trial_parse(table: interfaces.ParseTable, sentence, *, language=None):
	"""
	This quick-and-dirty trial parser will tell you if a sentence is a member of the language by throwing
	an exception otherwise. It leaves out everything to do with semantic values or parse trees.
	If you want to wrap your head around shift/reduce parsing, this is where to start.
	"""
	
	def prepare_to_shift(terminal_id) -> int:
		while True:
			step = table.get_action(stack[-1], terminal_id)
			if step > 0: return step  # Shift Action
			elif step == 0: raise interfaces.ParseError()  # Error Action
			else:  # Reduce Action
				nonterminal_id, length, message = table.get_rule(-1 - step)
				del stack[len(stack) - length:]  # Python hiccup: don't let epsilon rules delete the whole stack.
				stack.append(table.get_goto(stack[-1], nonterminal_id))
	
	stack = [table.get_initial(language) if language else 0]
	for symbol in sentence: stack.append(prepare_to_shift(table.get_translation(symbol)))
	prepare_to_shift(0)
	assert len(stack) == 2


def parse(table: interfaces.ParseTable, combine, each_token, *, language=None, interactive=False):
	"""
	The canonical table-driven LR parsing algorithm. As much as possible is left abstract.
	Perhaps unfortunately, there's no explicit support for location tracking here, although
	in some sense that can be left to the tokenizer and the combiner.
	:param table: The algorithm cares not where they came from or how they are represented.
	:param combine: Responsible to provide the result of a reduction on the attribute stack.
	:param each_token: Iterable source of <terminal, attribute> pairs.
	:param language: Choice of starting language, for multi-language tables.
	:param interactive: Whether the parser should reduce interactively.
	:return: Whatever the last combine(...) call returns as the semantic value of the sentence.
	"""
	state_stack, attribute_stack = [0 if language is None else table.get_initial(language)], []
	def tos() -> int: return state_stack[-1]
	def reduce(rule_id):
		assert rule_id >= 0
		nonterminal_id, length, message = table.get_rule(rule_id)
		attribute = attribute_stack[-1] if message is None else combine(message, attribute_stack)
		if length:
			del state_stack[-length:]
			del attribute_stack[-length:]
		state_stack.append(table.get_goto(tos(), nonterminal_id))
		attribute_stack.append(attribute)
	def prepare_to_shift(terminal_id) -> int:
		while True:
			step = table.get_action(tos(), terminal_id)
			if step >= 0: break
			reduce(-step-1) # Bison parsers offset the rule data to save a decrement, but that breaks abstraction.
		if step == 0: raise interfaces.ParseError([table.get_breadcrumb(q) for q in state_stack[1:]], symbol if terminal_id else '<<END>>')
		return step
	for symbol, attribute in each_token:
		state_stack.append(prepare_to_shift(table.get_translation(symbol)))
		attribute_stack.append(attribute)
		if interactive:
			while True:
				step = table.interactive_step(tos())
				if step < 0: reduce(-step-1)
				else: break
	prepare_to_shift(0)
	return attribute_stack[0]

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
		text, automaton, rules = self.__text, self.__automaton, self.__rules
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
				token = rules.unmatched(self, text[self.__start])
			else:
				self.__mark = mark
				trail = rules.get_trailing_context(rule_id)
				if trail is None: self.__bol = text[mark-1] in '\r\n'
				else: self.less(trail)
				token = rules.invoke(self, rule_id)
			if token is not None: yield token
			self.__start = self.__mark
		# Now determine if an end-of-file rule needs to execute:
		q = automaton.get_next_state(self.__condition[self.__bol], -1)
		if q>=0:
			token = rules.invoke(self, automaton.get_state_rule_id(q))
			if token is not None: yield token
	def current_position(self) -> int:
		""" As advertised. This was motivated by a desire to produce helpful error messages. """
		return self.__start