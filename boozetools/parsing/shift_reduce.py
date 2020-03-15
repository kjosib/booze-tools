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
	If you want to wrap your head around shift/reduce parsing, this is one way to start.
	
	However, you might find class PushDownAutomaton (below) a better bet for understanding.
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
	
	stack = [table.get_initial(language)]
	for symbol in sentence: stack.append(prepare_to_shift(table.get_translation(symbol)))
	prepare_to_shift(0)
	assert len(stack) == 2

class PushDownAutomaton:
	"""
	A real treatment of LR-family parsing algorithms should be given in terms
	of that model of computation called a "Push-Down Automaton" (PDA).
	
	In concept, a PDA is a sort of state machine with a stack.
	It has two essential moves:
	* "shift" adds a symbol to the top of the stack.
	* "reduce" groups sub-phrases into non-terminal symbols at top-of-stack.
	
	In the trial- parse mechanism above, we simulate the PDA with a simple
	list of states. However, for doing any sort of semantic analysis, we're
	going to want something a little nicer: the stack contains both states
	and semantic values under construction.
	
	Finally,
	"""
	
	def shift(self, state, semantic):
		"""
		The most fundamental operation on a PDA is to shift a symbol and a
		semantic value. Actually we don't shift symbols but states; these
		states encode some amount of left-context and are enough to decide
		how to respond to the input.
		"""
		self.stack.append((self.state, semantic))
		self.state = state
	
	def reduce_by_rule(self, rule_id):
		"""
		When the parser recognizes the right-hand-side of a production rule,
		this is the complete process for converting the sub-phrase to its
		non-terminal symbol on the stack.
		"""
		nonterminal_id, length, constructor_id, view = self.table.get_rule(rule_id)
		# In a nod to practical brevity, this supports a concise mechanism for
		# (not-eliminated) "unit/renaming" rules and "bracketing" rules:
		#    a negative constructor ID is where in the stack to look for a
		#    representative semantic value.
		if constructor_id < 0: semantic = self.stack[constructor_id][1]
		#    otherwise, the constructor ID indexes into a table of messages
		#    which the combiner is responsible to consult.
		else: semantic = self.combine(constructor_id, self.semantic_view(view))
		self.pop_phrase(length)
		self.shift(self.table.get_goto(self.state, nonterminal_id), semantic)

	def parse(self, token_stream, *, language=None):
		"""
		This is the part they explain in all the books:
		By reference to the "look-ahead" (terminal) symbol and the current
		state of the machine, the parse table tells the machine how to act.

		:param token_stream: Iterable source of <terminal, semantic> pairs.
			Most normally you'll supply a Scanner, but this version of the
			algorithm makes no such assumption.
		
		:param language: Choice of start-symbol, for multi-language tables.
		
		:return:
			if parsing succeeds: the correct semantic value of the input.
			if error recovery succeeds: the error-ridden semantic value.
			if the error channel propagates an exception: exceptionally.
			otherwise: `None`, and the stack will reflect the failure point.
		"""
		self.stack.clear()
		self.state = self.table.get_initial(language)
		self.input = iter(token_stream)
		terminal_id, semantic = self.next_token()
		while True:
			action = self.table.get_action(self.state, terminal_id)
			if action < 0: self.reduce_by_rule(-action-1)
			elif action == 0:
				if not self.handle_error(terminal_id, semantic):
					return
			elif terminal_id == 0: # End-marker for token stream.
				assert len(self.stack) == 1
				return self.stack.pop()[1]
			else:
				self.shift(action, semantic)
				self.perform_immediate_reductions()
				terminal_id, semantic = self.next_token()
			
	
	def next_token(self):
		""" Hopefully no surprises here. Adapt a token stream to sentinel mode... """
		try: symbol, semantic = next(self.input)
		except StopIteration: return 0, None
		else: return self.table.get_translation(symbol), semantic
	
	def __init__(self, table: interfaces.ParseTable, combine, error_channel:interfaces.ErrorChannel):
		"""
		This is sort of an "algorithm-as-object".
		Build the PDA and call its `.parse(...)` method as many times as you like.

		:param table: Satisfy the ParseTable interface however you like.
		
		:param combine: Gets called with a rule-ID and selected right-hand-side
			semantic elements; must return the semantic value for the left-hand
			side of the corresponding rule. Both mini-parse and the runtime
			support module for MacroParse provide code to help with this part.
		
		:param error_channel: Once I get error recovery implemented, this
			will be how you direct the parser to report error events.
		"""
		self.table = table
		self.combine = combine
		self.error_channel = error_channel
		self.stack, self.state, self.input = [], None, None
	
	def pop_phrase(self, length:int):
		"""
		When a phrase (the right-hand side of a production rule) has been
		recognized, the machine must remove the components of that phrase
		from the stack before shifting the corresponding non-terminal
		symbol (or rather, state) in its place.
		"""
		# Python hiccup: don't let epsilon rules delete the whole stack.
		if length:
			self.state = self.stack[-length][0]
			del self.stack[-length:]
	
	def semantic_view(self, view):
		"""
		Our grammar rules have annotation for which sub-phrases are
		significant to syntax-directed transduction. (Additionally,
		mid-rule actions are shown their significant bits of left-context.)
		The annotations form part of the rule set in the parse tables.
		"""
		return [self.stack[offset][1] for offset in view]
	
	def perform_immediate_reductions(self):
		"""
		Textbook exposition of shift-reduce parsing may fail to mention the
		practical importance of this step for real-world applications.
		
		Each time the parser shifts a token, it ought to perform interactive
		reductions until another token is strictly necessary to make a
		decision. If you forgo this, then ALL semantic actions (not just the
		ones that hinge on look-ahead) will be delayed by one lexical token.
		This can ruin interactive behavior (think of the desk-calculator)
		and also make it more complicated to report the causes of errors.
		
		It used to be said that this step might impact parser performance.
		Even if true, the difference would be negligible in most contexts.
		"""
		while True:
			action = self.table.interactive_step(self.state)
			if action < 0: self.reduce_by_rule(-action-1)
			else: break
	
	def handle_error(self, terminal_id, semantic):
		"""
		It's time to attempt a parser that can recover smartly from erroneous inputs.
		For a full exposition of the intended strategy, please see the document at:
		https://github.com/kjosib/booze-tools/blob/master/docs/Context%20Free%20Error%20Recovery.md
		
		That's not for today.
		"""
		stack_symbols = [self.table.get_breadcrumb(state) for state, sem_val in self.stack[1:]]
		stack_symbols.append(self.table.get_breadcrumb(self.state))
		raise interfaces.ParseError(stack_symbols, self.table.get_terminal_name(terminal_id), semantic)
		pass # TODO: Meanwhile, this is just an adaptation of what went before.

def parse(table: interfaces.ParseTable, combine, each_token, *, language=None):
	pda = PushDownAutomaton(table, combine, interfaces.ErrorChannel())
	return pda.parse(each_token, language=language)
