"""
Generalized-LR parsing amounts to direct simulation of a non-deterministic handle-finding
automaton (HFA). There are two key design decisions: How to represent the stack(s), and how
to orchestrate the operation of semantic actions. In other tools there are various approaches
taken. I'd like to survey those approaches, comment on their strengths and weaknesses, and
provide the ability to choose among them according to your specific parsing needs.

It's about this point that the necessary interface to a non-deterministic parse table is
made plain: GOTO can work just like in the deterministic case (because it's not affected
by non-determinism) but ACTION needs the additional skill to store non-deterministic
entries. There are a thousand ways to do it. One way? Any instruction greater than
the maximum valid state number refers instead to a "non-determinism" entry consisting
of a list of shift/reduce instructions.

A non-deterministic stack can be understood as a directed acyclic graph with a single "sink"
node representing the bottom of the stack. Each node is labeled with an HFA state and some
analogue to a "semantic value", the details of which depend on how clever you're being.
The reaching-symbols along each path from a "source" node to the sink represents a potential
viable prefix of a rightmost derivation. Each subsequent token may invalidate some paths and
create additional ambiguity along others. If all paths die, the input is not a member of the
language. If more than one path remains when the input and end-marker are all consumed, then
the input has more than one valid interpretation. Depending on your application, such a
situation may or may not be a problem.

At relatively low levels of ambiguity, it's reasonable to let each state have one distinct
semantic value, computed bottom-up during the parse: the graph is thus an inverted tree.
This approach is easy to understand, easy to code, and potentially leads to exponential
behavior. Still, it's usually just fine for grammars that are just barely out of reach for
a deterministic parse table. In this strategy, either the semantic actions must be pure
functions or else the parser must perform certain gymnastics to delay the invocation of
actions until any ambiguity is resolved.

At the opposite extreme, the top of the stack is organized to contain at most one node per
state-id, and all intermediate semantic values are structured to reflect ambiguity. The result
of such a parse represents a non-deterministic tree whose yield is the sequence of terminals.
This keeps algorithmic complexity down during parsing, which is great for highly-ambiguous
grammars, but then the semantic analysis code must deal sensibly with that ambiguity.

An interesting middle ground says the top-of-stack can be ambiguous a'la case two (the previous
paragraph) but the non-determinism must be resolved for each node bottom-up so that a given
node has at most one semantic value.
"""

from ..support import interfaces

NODE_STATE = 0
NODE_PRIOR = 1
NODE_SEMANTIC = 2

class BruteForceAndIgnorance:
	"""
	There is an old adage in software development: when in doubt, use brute force. Accordingly,
	the first implementation will be simple, easy to code, slow, and vulnerable to exponential
	behavior. However, it will also provide a fine basis of comparison for other approaches.
	
	This is the "inverse tree" approach: each node is a state, a predecessor, and a semantic
	value for the reaching-symbol -- except for the sink, which is special. The top-of-stack
	is just a list of currently-viable sub-stacks. This is usually sufficient for cases that
	are actually unambiguous but just not quite LR(1)-deterministic.
	
	Big problems with this approach, in no particular order, include:
		1. It fails to coalesce parse stacks that reduce to a common state.
		2. It eagerly calls reductions, even for dead-end parse attempts.
	
	So you can read what's going on:
		self.__tos contains nodes representing currently active parses.
		self.__next gets filled with the results of SHIFT actions.
		Each node is a tuple of (state_id, prior_node, semantic_value), accessed
			by field numbers given as the global constants above.
	"""
	def __init__(self, table: interfaces.ParseTable, driver, language=None):
		""" Please note this takes a driver not a combiner: it does its own selection of arguments from the stack. """
		self.__table = table
		self.__driver = driver
		self.__nr_states = table.get_split_offset()
		self.__tos = [(table.get_initial(language), None, None)]
	
	def consume(self, terminal, semantic):
		""" Call this from your scanning loop. """
		self.__consume(self.__table.get_translation(terminal), semantic)
		if not self.__tos: raise interfaces.GeneralizedParseError("Parser died midway at something ungrammatical.")

	def __consume(self, terminal_id, semantic):
		self.__next = []
		while self.__tos:
			top = self.__tos.pop()
			self.__act(self.__table.get_action(top[NODE_STATE], terminal_id), top, semantic)
		self.__tos = self.__next

	def finish(self) -> list:
		"""
		Call this after the last token to wrap up and
		:return: a valid semantic value for the parse.
		"""
		self.__consume(0, None)
		if self.__tos: return [top[NODE_PRIOR][NODE_SEMANTIC] for top in self.__tos]
		else: raise interfaces.GeneralizedParseError("Parser recognized a viable prefix, but not a complete sentence.")
	
	def __act(self, action, top, semantic):
		if action == 0: return # This branch of the stack dies.
		elif action < 0: self.__tos.append(self.__reduction(-1 - action, top))
		elif action < self.__nr_states: self.__shift(action, top, semantic)
		else:
			for alternative in self.__table.get_split(action - self.__nr_states):
				self.__act(alternative, top, semantic)
	
	def __shift(self, state_id, top, semantic):
		shift = state_id, top, semantic
		while True:
			action = self.__table.interactive_step(shift[NODE_STATE])
			if action < 0: shift = self.__reduction(-1 - action, shift)
			else: break
		self.__next.append(shift)
	
	def __reduction(self, rule_id, top):
		nonterminal_id, length, message = self.__table.get_rule(rule_id)
		if message is None: semantic = top[NODE_SEMANTIC]
		else:
			method, view = message
			args = BruteForceAndIgnorance.__view(top, view)
			if method is not None: semantic = getattr(self.__driver, method)(*args)
			elif len(view) == 1: semantic = args[0] # Bracketing rule
			else: semantic = tuple(args)
		while length > 0:
			length -= 1
			top = top[NODE_PRIOR]
		return self.__table.get_goto(top[NODE_STATE], nonterminal_id), top, semantic
	
	@staticmethod
	def __view(top, view):
		"""
		Recall that each element of view is a negative offset from the end of a notional
		linked-list-style stack, so in particular -1 is top-of-stack, and also these are
		presently constrained to appear in increasing order (starting negative and
		growing closer to zero).
		"""
		result = []
		depth = -1
		for seeking in reversed(view):
			while depth > seeking:
				depth -= 1
				top = top[NODE_PRIOR]
			result.append(top[NODE_SEMANTIC])
		result.reverse()
		return result