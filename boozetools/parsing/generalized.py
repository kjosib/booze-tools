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

class AbstractGeneralizedParser:
	"""
	Before I get too deep into it, let's lay out the general structure of a generalized parse:
	"""
	def __init__(self, table: interfaces.ParseTable, combine, language=None):
		""" Please note this takes a driver not a combiner: it does its own selection of arguments from the stack. """
		self._table = table
		self._combine = combine
		self._nr_states = table.get_split_offset()
		self.reset(table.get_initial(language))
	
	def reset(self, initial_state):
		""" Configure the initial stack situation for the given initial automaton state. """
		raise NotImplementedError(type(self))
	
	def consume(self, terminal, semantic):
		""" Call this from your scanning loop. """
		raise NotImplementedError(type(self))

	def finish(self) -> list:
		"""
		Call this after the last token to wrap up and
		:return: a valid semantic value for the parse.
		"""
		raise NotImplementedError(type(self))


class BruteForceAndIgnorance(AbstractGeneralizedParser):
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
			by field numbers given as the constants below.
	"""
	
	NODE_STATE = 0
	NODE_PRIOR = 1
	NODE_SEMANTIC = 2
	
	def reset(self, initial_state):
		self.__tos = [(initial_state, None, None)]
	
	def consume(self, terminal, semantic):
		self.__consume(self._table.get_translation(terminal), semantic)
		if not self.__tos: raise interfaces.GeneralizedParseError("Parser died midway at something ungrammatical.")

	def __consume(self, terminal_id, semantic):
		self.__next = []
		while self.__tos:
			top = self.__tos.pop()
			self.__act(self._table.get_action(top[self.NODE_STATE], terminal_id), top, semantic)
		self.__tos = self.__next

	def finish(self) -> list:
		"""
		Call this after the last token to wrap up and
		:return: a valid semantic value for the parse.
		"""
		self.__consume(0, None)
		if self.__tos: return [top[self.NODE_PRIOR][self.NODE_SEMANTIC] for top in self.__tos]
		else: raise interfaces.GeneralizedParseError("Parser recognized a viable prefix, but not a complete sentence.")
	
	def __act(self, action, top, semantic):
		""" There are four kinds of action: die, shift, reduce-and-shift, or split into parallel alternatives. """
		if action == 0: return # This branch of the stack dies.
		elif action < 0: self.__tos.append(self.__reduction(-1 - action, top))
		elif action < self._nr_states: self.__shift(action, top, semantic)
		else:
			for alternative in self._table.get_split(action - self._nr_states):
				self.__act(alternative, top, semantic)
	
	def __shift(self, state_id, top, semantic):
		shift = state_id, top, semantic
		while True:
			action = self._table.interactive_step(shift[self.NODE_STATE])
			if action < 0: shift = self.__reduction(-1 - action, shift)
			else: break
		self.__next.append(shift)
	
	def __reduction(self, rule_id, top):
		nonterminal_id, length, cid, view = self._table.get_rule(rule_id)
		if cid < 0: semantic = self.__view(top, (cid,))[0]
		else:
			args = self.__view(top, view)
			semantic = self._combine(cid, args)
		while length > 0:
			length -= 1
			top = top[self.NODE_PRIOR]
		return self._table.get_goto(top[self.NODE_STATE], nonterminal_id), top, semantic
	
	def __view(self, top, view):
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
				top = top[self.NODE_PRIOR]
			result.append(top[self.NODE_SEMANTIC])
		result.reverse()
		return result

def gss_trial_parse(table: interfaces.ParseTable, sentence, *, language=None):
	"""
	By now we've seen two ways each to do both recognition and semantic recovery:
	
	In module parsing.shift_reduce, the trial_parse(...) and parse(...) functions
	show the linear-time approach appropriate to unambiguous parse tables -- i.e.
	those which either have no CF-grammar inadequacies, or for which all such are
	suitably resolved with operator-precedence/associativity declarations.
	
	In module parsing.automata, the trial_parse(...) method of class HFA shows
	a simple recognizer, and the above-styled "brute force and ignorance" class
	shows a simple semantic recovery method, both suitable principally for getting
	our feet wet with the issues involved in dealing with ambiguous parse tables.
	
	It's time to do better. In 1988, Tomita showed the world how to use a so-called
	"graph-structured stack" to avoid the exponential behaviour associated with
	the brute-force approach. I'd like to implement that approach -- first with
	a recognizer and only then, once the essential algorithm is absolutely clear,
	as a full-on parser.
	
	This function is that recognizer.
	
	Interestingly, timings show the BF&I class to be slightly faster than this
	for inputs with only mild levels of ambiguity.
	"""
	nr_states = table.get_split_offset()
	
	class Node: # Nodes do have SOME structure. This should be adequate.
		__slots__ = ["state_id", "edges"]
		def __init__(self, state_id: int, edges:set):
			self.state_id = state_id  # encodes also the reaching symbol
			self.edges = edges
		def all_paths(self, length:int):
			if length < 1: yield self
			else:
				for p in self.edges: yield from p.all_paths(length - 1)
		def __repr__(self): return "<%d / %s>"%(self.state_id, ",".join(str(e.state_id) for e in self.edges))
	
	def act_on(node:Node, instruction:int):
		if instruction == 0: return
		elif instruction < 0: perform_reduction(node, -1-instruction)
		elif instruction < nr_states: # Shift the token:
			# Here, combining happens naturally because `shifts` is keyed to the destination state.
			if instruction in shifts: shifts[instruction].edges.add(node)
			else: shifts[instruction] = Node(instruction, {node})
		
		else: # There are multiple possibilities: split into multiple states as needed.
			for alternative in table.get_split(instruction - nr_states):
				act_on(node, alternative)
	
	def perform_reduction(node:Node, rule_id:int):
		"""
		This is a bit of a mind-bender, because it needs to do the right thing about
		both combining AND local-ambiguity packing. So here's the key insight:
		Local-ambiguity packing closely related to combining, but with respect to
		predecessors rather than the top-of-stack.
		
		Observation:
		The problem gets considerably harder if we have to select a "winning" parse
		and keep track of semantic values. Combining goto_target_node is the reason why
		semantic values go on edges, but this is only necessary for states reached by GOTO.
		Those reached by SHIFT might do as well to have a single semantic shared among
		all predecessors.
		
		Oh yes, one last thing: I seem to recall there's an ordering constraint.
		I think if you perform the shortest reductions first, the right things happen.
		Can this be encoded in the sequence of alternatives given?
		"""
		nonterminal_id, length, cid, view = table.get_rule(rule_id)
		for origin_node in node.all_paths(length):
			goto_state_id = table.get_goto(origin_node.state_id, nonterminal_id)
			if goto_state_id in top_of_stack:
				# At this point, if origin_node is already present, then local
				# ambiguity is indicated. For a recognizer, that is "packed" simply enough.
				top_of_stack[goto_state_id].edges.add(origin_node)
			else:
				goto_target_node = Node(goto_state_id, {origin_node})
				top_of_stack[goto_state_id] = goto_target_node
				queue.append(goto_target_node)
	
	initial_node = Node(table.get_initial(language), set())
	top_of_stack = {initial_node.state_id: initial_node}
	for symbol in sentence:
		shifts, queue = {}, list(top_of_stack.values())
		terminal_id = table.get_translation(symbol)
		for node in queue: act_on(node, table.get_action(node.state_id, terminal_id))
		if not shifts: raise interfaces.GeneralizedParseError("Parser died midway at something ungrammatical.")
		top_of_stack = shifts
	# Now deal with the end-of-input:
	shifts, queue = {}, list(top_of_stack.values())
	terminal_id = 0
	for node in queue: act_on(node, table.get_action(node.state_id, terminal_id))
	if not shifts: raise interfaces.GeneralizedParseError("Parser recognized a viable prefix, but not a complete sentence.")
	assert len(shifts) == 1
	return

