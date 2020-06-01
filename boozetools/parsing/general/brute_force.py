from ...support import interfaces

class BruteForceAndIgnorance(interfaces.AbstractGeneralizedParser):
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
		Each node is a tuple of (from_state_id, prior_node, semantic_value), accessed
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
