from ...support import interfaces


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
		def all_paths(self, depth:int):
			"""
			A previous version of this subroutine had potentially exponential
			behavior. It was just a naive depth-first traversal. A GSS can
			branch and merge, so a level-by-level approach seems better.
			"""
			frontier = {self}
			for _ in range(depth):
				frontier = set().union(*(N.edges for N in frontier))
			return frontier
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

