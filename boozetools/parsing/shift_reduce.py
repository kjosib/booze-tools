"""
This file gives the essential shift-reduce algorithm for parsing with with LR-family parse tables.
The exact form of the table is not important to this exposition, so this module treats the parse
table as an abstract data type defined and implemented elsewhere.
"""

from ..support import interfaces


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
			elif step == 0:
				stack_symbols = [table.get_breadcrumb(q) for q in stack[1:]]
				raise interfaces.ParseError(stack_symbols, symbol if terminal_id else '<<END>>', None)  # Error Action
			else:  # Reduce Action
				nonterminal_id, length, message = table.get_rule(-1 - step)
				del stack[len(stack) - length:]  # Python hiccup: don't let epsilon rules delete the whole stack.
				stack.append(table.get_goto(stack[-1], nonterminal_id))
	
	stack = [table.get_initial(language) if language else 0]
	for symbol in sentence: stack.append(prepare_to_shift(table.get_translation(symbol)))
	prepare_to_shift(0)
	assert len(stack) == 2


def parse(table: interfaces.ParseTable, combine, each_token, *, language=None, interactive=True):
	"""
	The canonical table-driven LR parsing algorithm. As much as possible is left abstract.
	Perhaps unfortunately, there's no explicit support for location tracking here, although
	in some sense that can be left to the tokenizer and the combiner.
	:param table: The algorithm cares not where they came from or how they are represented.
	:param combine: Responsible to provide the result of a reduction on the semantic stack.
	:param each_token: Iterable source of <terminal, semantic> pairs.
	:param language: Choice of starting language, for multi-language tables.
	:param interactive: Whether the parser should reduce interactively.
	:return: Whatever the last combine(...) call returns as the semantic value of the sentence.
	"""
	state_stack, semantic_stack = [0 if language is None else table.get_initial(language)], []
	def tos() -> int: return state_stack[-1]
	def reduce(rule_id):
		assert rule_id >= 0
		nonterminal_id, length, message = table.get_rule(rule_id)
		attribute = semantic_stack[-1] if message is None else combine(message, semantic_stack)
		if length:
			del state_stack[-length:]
			del semantic_stack[-length:]
		state_stack.append(table.get_goto(tos(), nonterminal_id))
		semantic_stack.append(attribute)
	def prepare_to_shift(terminal_id) -> int:
		while True:
			step = table.get_action(tos(), terminal_id)
			if step < 0: reduce(-step-1) # Bison parsers offset the rule data to save a decrement, but that breaks abstraction.
			elif step > 0: return step
			else:
				stack_symbols = [table.get_breadcrumb(q) for q in state_stack[1:]]
				if terminal_id: raise interfaces.ParseError(stack_symbols, symbol, semantic)
				else: raise interfaces.ParseError(stack_symbols, '<<END>>', None)
	for symbol, semantic in each_token:
		state_stack.append(prepare_to_shift(table.get_translation(symbol)))
		semantic_stack.append(semantic)
		if interactive:
			while True:
				step = table.interactive_step(tos())
				if step < 0: reduce(-step-1)
				else: break
	prepare_to_shift(0)
	return semantic_stack[0]

