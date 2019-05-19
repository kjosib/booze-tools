"""
GLR is basically the non-deterministic version of LR parsing.

As a parsing strategy, it's amenable to the use of parse tables produced by any viable LR algorithm.
The more powerful table-construction algorithms result in comparatively fewer blind alleys for
a GLR runtime to explore.

Building a deterministic parse table can be seen as first building a non-deterministic one and
then taking a further step to resolve any conflicts. That is why I'm going down this alley.

Towards the end of this module is a test-parse routine which exercises these GLR-type constructions.
"""
import collections
from typing import NamedTuple, Callable, Sequence, Iterable
from . import context_free, foundation, interfaces

END = '<END>' # An artificial "end-of-text" terminal-symbol.

class GLR0:
	"""
	This is not a method-of-CFG: that would have the wrong connotation. A grammar
	specification is like a model, and this is more like a (complicated) view.
	The heavy lifting is all done in the constructor.
	
	In principle you could drive a Tomita-style parser with this table and the
	grammar definition. Over in the unit tests lives something vaguely reminiscent.
	
	Fields are:
		graph: a list of GLR0_State objects; their index is implicitly their node ID.
		initial: a list of initial-state ID numbers (graph node indices) corresponding
			to the start-symbols of the CFG.
		accept: a list of final/accepting-state ID numbers (graph node indices) also
			corresponding to the start-symbols of the CFG.
	"""
	
	class State(NamedTuple):
		shift: dict  # symbol => state-id
		reduce: set  # rule-id
	
	__slots__ = ['graph', 'initial', 'accept']
	def __init__(self, grammar:context_free.ContextFreeGrammar):
		"""
		Basically, this is a breadth-first graph exploration/construction.
		This variety of parse automaton does not consider look-ahead.
		"""
		
		def optimize_unit_rules(step:dict, check:dict) -> dict:
			# A unit-rule is eligible to be elided (optimized-to-nothing) exactly when
			# the state reached by shifting the RHS would have no other active parse items.
			# We don't actually traverse such states, but instead redirect the corresponding
			# shift-entry, essentially running the unit-rule at table-generation time.
			
			# If performing this task while carrying look-ahead in the parse-items, it sufficient
			# that the same criteria would have applied had the look-ahead not been involved.
			replace = {s: grammar.rules[r].lhs for s, r in check.items() if len(step[s]) == 1}
			shifts = {}
			for symbol in step.keys():
				proxy = symbol
				while proxy in replace: proxy = replace[proxy]
				shifts[symbol] = bft.lookup(frozenset(step[proxy]), breadcrumb=proxy)
			return shifts
		
		def build_state(core: frozenset):
			step, check, reduce = collections.defaultdict(set), {}, set()
			def visit(item):
				rule_id, position = item
				if position < len(RHS[rule_id]):
					next_symbol = RHS[rule_id][position]
					step[next_symbol].add((rule_id,position+1))
					if rule_id in unit_rules and position == 0: check[next_symbol] = rule_id
					return symbol_front.get(next_symbol)
				elif rule_id<len(grammar.rules): reduce.add(rule_id)
			foundation.transitive_closure(core, visit)
			self.graph.append(GLR0.State(
				shift=optimize_unit_rules(step, check),
				reduce=reduce,
			))
		
		assert grammar.start
		##### Start by arranging most of the grammar data in a convenient form:
		RHS = [rule.rhs for rule in grammar.rules] # This soon gets augmented internal to this algorithm.
		unit_rules = set(i for i, rule in enumerate(grammar.rules) if rule.attribute is None and len(rule.rhs) == 1)
		def front(rule_ids): return frozenset([(r,0) for r in rule_ids])
		symbol_front = {symbol: front(rule_ids) for symbol, rule_ids in grammar.symbol_rule_ids.items()}
		bft = foundation.BreadthFirstTraversal()
		self.graph = []
		# Initial-state cores refer only to the "augmentation" rule -- which has no LHS in this manifestation.
		self.initial = [bft.lookup(front([foundation.allocate(RHS, [language])])) for language in grammar.start]
		bft.execute(build_state)
		self.accept = [self.graph[qi].shift[language] for qi, language in zip(self.initial, grammar.start)]
	
	def traverse(self, q:int, symbols) -> int:
		""" Starting in state q, follow the shifts for symbols, and return the resulting state ID. """
		for s in symbols: q = self.graph[q].shift[s]
		return q
	
	def display(self, grammar:context_free.ContextFreeGrammar):
		for q, state in enumerate(self.graph):
			print(q, state.shift, state.reduce)
	
	def trial_parse(self, cfg: context_free.ContextFreeGrammar, sentence):
		return trial_parse(self.initial[0], self.accept[0], self.graph, lambda state, lexeme:state.reduce, cfg.rules, sentence)


class GLALR:
	"""
	Building a non-deterministic LALR(1)-style table is a direct extension of the GLR(0)
	construction. The main objective is to figure out which look-ahead tokens are relevant
	to reduce rules. I'm not going to worry about precedence declarations at this point.
	If we stop here, we get a table that's more efficient than GLR(0) for generalized
	parsing because it will not attempt a trial reduction if LALR says the look-ahead
	token definitely would not be shift-able in any event.
	
	The bulk of the work here consists of constructing first- and follow-sets. I take the
	approach of allocating a "follow set" for each place that a rule accepts, rather than
	one for each time a symbol gets elaborated. I suspect this is slightly more specific.
	"""
	
	class State(NamedTuple):
		shift: dict
		reduce: dict
		
	__slots__ = ['graph', 'initial', 'accept']
	
	def __init__(self, grammar:context_free.ContextFreeGrammar):
		lr0 = GLR0(grammar)
		self.initial, self.accept = lr0.initial, lr0.accept
		terminals = grammar.apparent_terminals()
		token_sets = [terminals.intersection(node.shift.keys()) for node in lr0.graph]
		for q in lr0.accept: token_sets[q].add(END) # Denoting that end-of-input can follow a sentence.
		# Allocate and track/label all follow sets:
		follow = {}
		for q, node in enumerate(lr0.graph):
			for rule_id in node.reduce:
				follow[q,rule_id] = foundation.allocate(token_sets, set())
		# Generate a token-set inflow graph with nodes as lists of inbound edges.
		inflow = [set() for _ in token_sets]
		for q, node in enumerate(lr0.graph):
			for symbol, target in node.shift.items():
				if symbol in grammar.symbol_rule_ids:
					for rule_id in grammar.symbol_rule_ids[symbol]:
						rule_end = lr0.traverse(q, grammar.rules[rule_id].rhs)
						inflow[rule_end].add(target)
						inflow[follow[rule_end, rule_id]].add(target)
		# Determine the contents of all first- and follow-sets:
		for component in foundation.strongly_connected_components_by_tarjan(inflow):
			tokens = set()
			for k in component:
				tokens.update(token_sets[k])
				tokens.update(*[token_sets[j] for j in inflow[k]])
				token_sets[k] = tokens
		# At this point, we could stop and make a GLALR table...
		def transmogrify(q:int, node:GLR0.State) -> GLALR.State:
			""" This doesn't worry about precedence declarations just yet... """
			reduce = {}
			for rule_id in node.reduce:
				for token in token_sets[follow[q, rule_id]]:
					if token not in reduce: reduce[token] = [rule_id]
					else: reduce[token].append(rule_id) # This branch represents an R/R conflict...
			return GLALR.State(node.shift, reduce)
		self.graph = [transmogrify(q, node) for q, node in enumerate(lr0.graph)]
	
	def trial_parse(self, cfg: context_free.ContextFreeGrammar, sentence):
		return trial_parse(self.initial[0], self.accept[0], self.graph, lambda state, lexeme:state.reduce.get(lexeme, ()), cfg.rules, sentence)


	
def trial_parse(initial:int, accept:int, graph:Sequence, reductions:Callable, rules:Sequence[context_free.Rule], sentence:Iterable):
	"""
	This is intended to be a super simplistic embodiment of some idea how to make a GLR parse engine.
	It exists only for unit-testing the GLR stuff, and therefore doesn't try to build a semantic value.

	The approach taken is a lock-step parallel simulation with a list of active possible stacks in
	cactus-stack form: each entry is a cons cell consisting of a state id and prior stack. This
	approach is guaranteed to work despite exploring all possible paths through the parse.

	This is an ABC: it gets (very slightly) specialized to deal with either GLR(0) or GLALR constructions.
	"""
	
	def reduce(stack, rule_id):
		""" To perform a reduction, roll the stack to before the RHS and then shift the LHS. """
		rule = rules[rule_id]
		for i in range(len(rule.rhs)): stack = stack[1]
		return graph[stack[0]].shift[rule.lhs], stack
	
	root = (initial, None)
	alive = [root]
	for lexeme in sentence:
		next = []
		for stack in alive:
			state = graph[stack[0]]
			if lexeme in state.shift: next.append((state.shift[lexeme], stack))
			for rule_id in reductions(state, lexeme): alive.append(reduce(stack, rule_id))
		alive = next
		if not alive: raise interfaces.ParseError("Parser died midway at something ungrammatical.")
	for stack in alive:
		if stack[0] == accept: return True
		for rule_id in reductions(graph[stack[0]], END): alive.append(reduce(stack, rule_id))
	raise interfaces.ParseError("Parser recognized a viable prefix, but not a complete sentence.")

