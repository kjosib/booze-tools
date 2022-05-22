"""
This file gives the essential shift-reduce algorithm for parsing with LR-family parse tables.
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


def trial_parse(table: interfaces.HandleFindingAutomaton, sentence, *, language=None):
	"""
	This quick-and-dirty trial parser will tell you if a sentence is a member of the language by throwing
	an exception otherwise. It leaves out everything to do with semantic values or parse trees.
	If you want to wrap your head around shift/reduce parsing, this is one way to start.
	"""
	
	def prepare_to_shift(terminal_id) -> int:
		while True:
			step = table.get_action(stack[-1], terminal_id)
			if step > 0: return step  # Shift Action
			elif step == 0:  # Error Action
				stack_symbols = [table.get_breadcrumb(q) for q in stack[1:]]
				raise ValueError(stack_symbols, symbol if terminal_id else interfaces.END_OF_TOKENS, None)
			else:  # Reduce Action
				nonterminal_id, length, constructor_id, view = table.get_rule(-1 - step)
				if length: # Python hiccup: don't let epsilon rules delete the whole stack.
					del stack[ - length:]
				stack.append(table.get_goto(stack[-1], nonterminal_id))
	
	stack = [table.get_initial(language)]
	for symbol in sentence: stack.append(prepare_to_shift(table.get_translation(symbol)))
	prepare_to_shift(table.get_translation(interfaces.END_OF_TOKENS))
	assert len(stack) == 2

class PushDownState:
	"""
	A real treatment of LR-family parsing algorithms should be given in terms
	of that model of computation called a "Push-Down Automaton" (PDA).
	
	In concept, a PDA is a sort of state machine with a stack.
	It has two essential moves:
	* "shift" adds a symbol (with semantic value) to the top of the stack.
	* "reduce" groups sub-phrases into non-terminal symbols at top-of-stack.
	
	In the trial-parse function above, we simulate the PDA with a simple
	list of states. However, for doing any sort of semantic analysis, we're
	going to want something a little nicer: the stack contains both states
	and semantic values under construction.
	
	That's the usual explanation, anyway. In fact "reduce" is better seen as
	a three-part operation: Combine the semantics near the top of the stack,
	pop symbols corresponding to the right-hand side of a production rule,
	and shift the head non-terminal for said rule. Most of that activity is
	more intimately connected with the specific application rather than the
	push-down mechanism, so this class just exposes appropriate primitives.
	The actual "automaton" per-se is the `parse(...)` function, below.
	
	Oh-by-the-way, we don't actually shift symbols per-se, because then
	identifying the correct time to reduce would amount to a search problem.
	Instead, we shift STATES from a characteristic finite-state automaton:
	these encode sufficient left-context to identify the correct places to
	perform a reduction. That FSA forms part of the parse table.
	"""
	
	def __init__(self, initial_state):
		self.stack, self.state = [], initial_state
	
	def shift(self, state, semantic):
		"""
		The most fundamental operation on a PDA is to shift a symbol and a
		semantic value. Actually we don't shift symbols but states; these
		states encode some amount of left-context and are enough to decide
		how to respond to the input.
		"""
		self.stack.append((self.state, semantic))
		self.state = state
	
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
	
	def one_semantic(self, offset:int):
		"""
		There's a common use-case where we just grab the semantic
		value at a specific offset from top-of-stack.
		"""
		return self.stack[offset][1]
	
	def succeed(self):
		""" Fetch the final summary semantic-value. """
		assert len(self.stack) == 1, (self.stack, self.state)
		return self.stack.pop()[1]
	
	def index_state(self, depth:int):
		""" Turns out sometimes we need the state N steps deep in the stack, for error recovery. """
		if depth<=0: return self.state
		else: return self.stack[-depth][0]
	
	def __len__(self):
		""" This is how many steps "deep" you can still find a state. """
		return 1 + len(self.stack)
	
	def path_from_root(self):
		""" Yield each state ID; sometimes useful in error reporting. """
		for state, semantic in self.stack: yield state
		yield self.state
	
class Hypothetical:
	"""
	In the context of error recovery, it's extremely handy to have a general
	"hypothetical parse" facility. This object latches on to an existing PDS
	and acts like a hypothetical branch of that PDS strictly for testing hypothesis.
	"""
	def __init__(self, table:interfaces.HandleFindingAutomaton, pds:PushDownState, initial_depth):
		self.table = table
		self.host = pds
		self.initial_depth = self.watermark = initial_depth
		self.suffix = []
	def tos(self):
		try: return self.suffix[-1]
		except IndexError: return self.host.index_state(self.watermark)
	def shift(self, state): self.suffix.append(state)
	def pop_phrase(self, length:int):
		if length > len(self.suffix):
			self.watermark = self.watermark + length - len(self.suffix)
			self.suffix = []
		elif length: del self.suffix[-length:]
	def reduce(self, rule_id):
		nonterminal_id, length, constructor_id, view = self.table.get_rule(rule_id)
		self.pop_phrase(length)
		self.shift(self.table.get_goto(self.tos(), nonterminal_id))
	def consume(self, terminal_id) -> int:
		""" Returns resulting top-of-stack or raises ValueError. """
		while True:
			step = self.table.get_action(self.tos(), terminal_id)
			if step < 0: self.reduce(-step-1)
			elif step == 0: raise ValueError
			else:
				self.shift(step)
				return step


def parse(table: interfaces.HandleFindingAutomaton, combine, token_stream, *, language=None, on_error:interfaces.ParseErrorListener):
	"""
		:param table: Satisfy the HandleFindingAutomaton interface however you like.
			By reference to the "look-ahead" (terminal) symbol and the current
			state of the PDA, the parse table tells the machine how to act.
		
		:param combine: Gets called with a rule-ID and selected right-hand-side
			semantic elements; must return the semantic value for the left-hand
			side of the corresponding rule. Both mini-parse and the runtime
			support module for MacroParse provide code to help with this part.
		
		:param token_stream: Iterable source of <terminal, semantic> pairs.
			Most normally you'll supply a Scanner, but this version of the
			algorithm makes no such assumption.
		
		:param language: Choice of start-symbol, for multi-language tables.
		
		:return:
			if parsing succeeds: the correct semantic value of the input.
			if error recovery succeeds: the error-ridden semantic value.
			if the error channel propagates an exception: exceptionally.
			otherwise: by `raise interfaces.ParseError(...)`
		
		:param on_error: Once I get error recovery implemented, this
			will be how you direct the parser to report error events.
	"""
	
	def basic_machine_cycle():
		"""
		This is the easy part they explain in all the books...
		
		Classically we might do this with a loop-and-a-half around a stream
		of tokens, treating end-of-text as a sentinel value. But iterators
		are much more the way of Python, so I've twisted the logic up to
		allow the StopIteration exception to do the right thing.
		"""
		for symbol, semantic in token_iterator:
			token_id = table.get_translation(symbol)
			action = find_shift(token_id)
			if action:
				pds.shift(action, semantic)
				perform_immediate_reductions()
			else:
				on_error.unexpected_token(symbol, semantic, pds)
				if not handle_error(token_id, semantic): return
		# After the last real symbol, the parser needs to prepare as if
		# about to shift a notional "end-of-text" symbol -- but don't
		# actually perform that shift: instead that's the signal of
		# an accepted sentence in the language.
		if not find_shift(sentinel_end):
			on_error.unexpected_eof(pds)
			if not handle_error(sentinel_end, None): return
		return pds.succeed()
	
	def find_shift(terminal_id):
		"""
		Before shifting each look-ahead terminal, the parser will reduce
		zero-or-more times until the ACTION table says which state to
		shift into for this terminal.
		"""
		while True:
			action = table.get_action(pds.state, terminal_id)
			if action < 0: reduce_by_rule(-action-1)
			else: return action
	
	def reduce_by_rule(rule_id):
		"""
		When the parser recognizes the right-hand-side of a production rule,
		this is the complete process for converting the sub-phrase to its
		non-terminal symbol on the stack.
		"""
		nonterminal_id, length, constructor_id, view = table.get_rule(rule_id)
		# In a nod to practical brevity, this supports a concise mechanism for
		# (not-eliminated) "unit/renaming" rules and "bracketing" rules:
		#    a negative constructor ID is where in the stack to look for a
		#    representative semantic value.
		if constructor_id < 0: semantic = pds.one_semantic(constructor_id)
		#    otherwise, the constructor ID indexes into a table of messages
		#    which the combiner is responsible to consult.
		else:
			args = pds.semantic_view(view)
			try: semantic = combine(constructor_id, args)
			except Exception as e:
				message = table.get_constructor(constructor_id)
				semantic = on_error.exception_parsing(e, message, args)
		pds.pop_phrase(length)
		pds.shift(table.get_goto(pds.state, nonterminal_id), semantic)

	def perform_immediate_reductions():
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
			action = table.interactive_step(pds.state)
			if action < 0: reduce_by_rule(-action-1)
			else: break
	
	def handle_error(terminal_id, semantic) -> bool:
		"""
		It's time to attempt a parser that can recover smartly from erroneous inputs.
		For a full exposition of the intended strategy, please see the document at:
		https://github.com/kjosib/booze-tools/blob/master/docs/Context%20Free%20Error%20Recovery.md
		
		:return True if the parser is able to resynchronize.
		"""
		avenues = paths_to_recovery()
		if not avenues:
			on_error.cannot_recover()
			return False
		
		if terminal_id == sentinel_end: success = try_proposal(avenues, [(sentinel_end, None)])
		else: success = any(try_proposal(avenues, p) for p in generate_proposals(terminal_id, semantic, 3))
		if not success: on_error.did_not_recover()
		return success
	
	def paths_to_recovery():
		"""
		We're in a situation where we need to shift the error token.
		We need to pop zero or more elements off the top of the stack before shifting.
		We won't know how many is best to pop until we find which gives the best (and smallest) recovery.
		So this function returns the candidates, fit for iteration over.
		"""
		#  nb: This relies on dictionary insertion order, which is assured in recent Python.
		avenues = {}
		for depth in range(len(pds)): # There's a madness to this un-pythonic method...
			if not table.get_action(pds.index_state(depth), error_token_id): continue
			try: recovery_state = contemplate_recovery(depth, ())
			except ValueError: continue
			if recovery_state not in avenues: avenues[recovery_state] = depth
		return tuple(avenues.items())
	def try_proposal(avenues, proposal):
		ts, vs = zip(*proposal)
		for recovery_state, depth in avenues:
			if table.get_action(recovery_state, ts[0]):  # i.e. the proposal has some hope of working here...
				try:
					contemplate_recovery(depth, ts)
				except ValueError:
					continue
				else:
					commit_recovery(depth, proposal)
					return True
	
	def contemplate_recovery(depth, terminal_ids) -> int:
		h = Hypothetical(table, pds, depth)
		h.consume(error_token_id)
		for t in terminal_ids: h.consume(t)
		return h.tos()
	
	def commit_recovery(depth, proposal):
		err_val = on_error.will_recover(proposal)
		pds.pop_phrase(depth)
		pds.shift(find_shift(error_token_id), err_val)
		for token_id, semantic in proposal:
			pds.shift(find_shift(token_id), semantic)
		if token_id == sentinel_end: pds.pop_phrase(1)
		
	
	def generate_proposals(terminal_id, semantic, length):
		# This generates overlapping rolling runs of tokens.
		proposal = [(terminal_id, semantic)]
		for symbol, value in token_iterator:
			proposal.append((table.get_translation(symbol), value))
			if len(proposal) >= length:
				yield proposal
				proposal.pop(0)
		proposal.append((sentinel_end, None))
		while proposal:
			yield proposal
			proposal.pop(0)
		
	
	sentinel_end = table.get_translation(interfaces.END_OF_TOKENS)
	error_token_id = table.get_translation(interfaces.ERROR_SYMBOL)
	pds = PushDownState(table.get_initial(language))
	token_iterator = iter(token_stream)
	return basic_machine_cycle()


