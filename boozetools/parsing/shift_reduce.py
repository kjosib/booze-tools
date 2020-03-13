"""
This file gives the essential shift-reduce algorithm for parsing with with LR-family parse tables.
The exact form of the table is not important to this exposition, so this module treats the parse
table as an abstract data type defined and implemented elsewhere.

A word on reductions:
-------------------------
There must be a table of rules consisting of:
	left-hand side non-terminal symbol (an ID number),
	rule length (the number of states to pop after computing the reduction),
	"message" -- generally, a "constructor" symbol and a vector of stack offsets to parameters.

As a minor optimization (or perhaps, dirty trick) in the past, I'd allowed the "message" portion
to be `None` as a hint that this was going to be a unit-reduction rule. However, I no longer think
that's best. Such renaming-rules are usually optimized out of the tables to begin with. Bracketing
rules are the next most common: those with only one non-void right-hand symbol. They are also a
superset of the few remaining unit-reductions, and common enough in practice.

Anyway, the new idea keeps the two parts of the message separate: `constructor_id, view`.
Bracketing rules are encoded with a negative `constructor_id`, and the combiner is responsible
for positive `constructor_id` numbers.
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
			elif step == 0:  # Error Action
				stack_symbols = [table.get_breadcrumb(q) for q in stack[1:]]
				raise interfaces.ParseError(stack_symbols, symbol if terminal_id else '<<END>>', None)
			else:  # Reduce Action
				nonterminal_id, length, constructor_id, view = table.get_rule(-1 - step)
				if length: # Python hiccup: don't let epsilon rules delete the whole stack.
					del stack[ - length:]
				stack.append(table.get_goto(stack[-1], nonterminal_id))
	
	stack = [table.get_initial(language) if language else 0]
	for symbol in sentence: stack.append(prepare_to_shift(table.get_translation(symbol)))
	prepare_to_shift(0)
	assert len(stack) == 2


def parse(table: interfaces.ParseTable, combine, each_token, *, language=None):
	"""
	The canonical table-driven LR parsing algorithm.
	
	For now this codes for the happy path and lets exceptions bubble out if
	anything goes wrong. That's fine for everything from toy problems to
	medium-sized applications, and it's what mini-parse uses. More robust
	error processing is coming.
	
	:param table: Satisfy the ParseTable interface however you like.
	
	:param combine: Gets called with a rule-ID and selected right-hand-side
		semantic elements; must return the semantic value for the left-hand
		side of the corresponding rule. Both mini-parse and the runtime
		support module for MacroParse provide code to help with this part.
	
	:param each_token: Iterable source of <terminal, semantic> pairs.
		Most normally you'll supply a Scanner, but this version of the
		algorithm makes no such assumption.
	
	:param language: Choice of starting language, for multi-language tables.
	
	:return: Whatever the last combine(...) call returns as the
		semantic value of the sentence.
	"""
	state_stack, semantic_stack = [0 if language is None else table.get_initial(language)], []
	def tos() -> int: return state_stack[-1]
	def shift(state, semantic):
		state_stack.append(state)
		semantic_stack.append(semantic)
	def reduce(rule_id):
		assert rule_id >= 0
		nonterminal_id, length, constructor_id, view = table.get_rule(rule_id)
		if constructor_id < 0: attribute = semantic_stack[constructor_id]
		else: attribute = combine(constructor_id, [semantic_stack[offset] for offset in view])
		if length: # Python hiccup: don't let epsilon rules delete the whole stack.
			del state_stack[-length:]
			del semantic_stack[-length:]
		shift(table.get_goto(tos(), nonterminal_id), attribute)
	def prepare_to_shift(terminal_id) -> int:
		while True: # Note the classic loop-and-a-half problem evinced here...
			step = table.get_action(tos(), terminal_id)
			if step < 0: reduce(-step-1) # Bison parsers offset the rule data to save a decrement, but that breaks abstraction.
			else: return step
	def reduce_eagerly():
		# Having shifted the token, the parser ought to perform interactive reductions
		# until another token is strictly necessary to make a decision. Such behavior
		# can be left out of batch-process parsers, but error reporting is affected.
		while True:
			step = table.interactive_step(tos())
			if step < 0: reduce(-step-1)
			else: break

	def notify_error(symbol, semantic):
		# FIXME: This is a hold-over from earlier...
		stack_symbols = [table.get_breadcrumb(q) for q in state_stack[1:]]
		raise interfaces.ParseError(stack_symbols, symbol or '<<END>>', semantic)

	def enter_error_mode():
		# FIXME: One obvious means of error recovery is:
		#  1. Roll the stack back until $error$ is shiftable.
		#  2. Shift $error$.
		#  3. Skip zero or more tokens until seeing something
		#     the parse table knows what to do with.
		#  4. Do that something.
		#  This is inadequate: good mechanism must scan the entire stack for
		#  possible recovery points. Setting up that recovery vector will be
		#  a separate exercise.
		#  The present system does none of these things.
		pass
	
	error_squelch = 0
	for symbol, semantic in each_token:
		terminal_id = table.get_translation(symbol)
		step = prepare_to_shift(terminal_id)
		if step > 0:
			shift(step, semantic)
			reduce_eagerly()
			if error_squelch: error_squelch -= 1
		else: # Error has been detected.
			if not error_squelch: notify_error(symbol, semantic)
			enter_error_mode()
			error_squelch = 3
	if prepare_to_shift(0) == 0: notify_error(None, None)
	else: return semantic_stack[0]

