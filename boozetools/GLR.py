"""
G-for-Generalized: GLR is basically the non-deterministic version of LR parsing.

As a parsing strategy, GLR means non-determinism is embraced and resolved as necessary at
in the context of actual parse runs. You can do GLR with any viable LR-style HFA, though
better tables naturally result in fewer blind alleys. In principle, the "trivial" table
is just the set of all grammar rules at every point: this yields classical Earley parsing.

Within this module, various handle-finding automaton (HFA) construction functions return a
(mostly) standardized structure which properly represents any remaining non-determinism.
Transmuting these to fully-deterministic structures is the LR module's job.

The HFA class itself contains a trial-parse routine which exercises these constructions
by determining whether they recognize a string as "in the language". It's great for testing
and illustrates one method to perform a parallel-parse, but it does not bother to recover a
parse tree or semantic value. Such things could be added, but preferably atop good means
for persisting ambiguous parse tables.
"""
import collections
from typing import NamedTuple, Callable, Sequence, Iterable, TypeVar, Generic, List, Dict, Set
from . import context_free, foundation, interfaces, pretty

END = '<END>' # An artificial "end-of-text" terminal-symbol.

T = TypeVar('T')

class HFA(Generic[T]):
	"""
	HFA is short for "Handle-Finding Automaton", which is clunky to repeat all over the place.
	
	What is a handle?
	
	A handle is that point in the text where the right end of a rule has been matched and
	recognition of the corresponding non-terminal symbol could be performed.
	
	There is a common base structure for these, and certain operations are largely similar
	regardless of which sort of table-construction algorithm is underway.
	
	The main difference between HFAs is what sort of object they use for states.
	To participate in the generic operations, states must have a "shift" dictionary mapping
	symbols to successor state numbers (not objects) and support state.reductions_before(lexeme)
	which must return an Iterable of zero or more rule-IDs.
	
	Fields are:
	graph: a list of state objects; their index is implicitly their node ID.
	initial: a list of initial-state ID numbers (graph node indices) corresponding
		to the start-symbols of the CFG.
	accept: a list of final/accepting-state ID numbers (graph node indices) also
		corresponding to the start-symbols of the CFG.
	grammar: The ContextFreeGrammar that started it all.
	bft: The BreadthFirstTraversal object which was used for the construction.
		This happens to be greatly useful in various diagnostic and other capacities.
	"""
	graph: List[T]
	initial: List[int]
	accept: List[int]
	grammar: context_free.ContextFreeGrammar
	bft: foundation.BreadthFirstTraversal
	
	def __init__(self, *, graph, initial, accept, grammar, bft):
		""" I don't want exactly named-tuple semantics. """
		self.graph, self.initial,self.accept, self.grammar, self.bft = graph, initial, accept, grammar, bft
	
	def display_situation(self, q: int, lookahead: str):
		"""
		Used for diagnostic displays:
			How might I get to state #q, in symbols?
			What would that parser situation look like?
		"""
		head, *tail = self.bft.shortest_path_to(q)
		print('==============\nIn language %r, consider:' % self.grammar.start[self.initial.index(head)])
		print('\t' + ' '.join(map(self.bft.breadcrumbs.__getitem__, tail)), pretty.DOT, lookahead)
	
	def traverse(self, q: int, symbols:Iterable) -> int:
		""" Starting in state q, follow the shifts for symbols, and return the resulting state ID. """
		for s in symbols: q = self.graph[q].shift[s]
		return q
	
	def trial_parse(self, sentence: Iterable):
		"""
		This is intended to be a super-simplistic non-deterministic recognizer: It exists only for
		unit-testing the GLR table-construction algorithms, and therefore doesn't try to build a
		semantic value or worry about pathological grammars.
		
		The approach taken is a lock-step parallel simulation with a cactus-stack of viable states:
		each entry is a cons cell consisting of a state id and prior stack. Because it explores
		every possible parse, it will diverge if faced with an infinitely-ambiguous situation.
		There are ways to cope with such cases, but in practice they are normally the result of
		mistakes, so the more useful response is to reject infinitely-ambiguous grammars.

		To play along, HFA states must support the .reductions_before(lexeme) method.
		"""
		
		language_index = 0 # Or perhaps: self.grammar.start.index[language_symbol]
		initial, accept = self.initial[language_index], self.accept[language_index]
		
		def reduce(stack, rule_id):
			""" To perform a reduction, roll the stack to before the RHS and then shift the LHS. """
			rule = self.grammar.rules[rule_id]
			for i in range(len(rule.rhs)): stack = stack[1]
			return self.graph[stack[0]].shift[rule.lhs], stack
		
		root = (initial, None)
		alive = [root]
		for lexeme in sentence:
			next = []
			for stack in alive:
				state = self.graph[stack[0]]
				if lexeme in state.shift: next.append((state.shift[lexeme], stack))
				for rule_id in state.reductions_before(lexeme): alive.append(reduce(stack, rule_id))
			alive = next
			if not alive: raise interfaces.ParseError("Parser died midway at something ungrammatical.")
		for stack in alive:
			q = stack[0]
			if q == accept: return True
			for rule_id in self.graph[q].reductions_before(END): alive.append(reduce(stack, rule_id))
		raise interfaces.ParseError("Parser recognized a viable prefix, but not a complete sentence.")

class LR0_State(NamedTuple):
	"""
	The LR(0) construction completely ignores look-ahead for reduce-rules, so for a
	non-deterministic parse table, it's enough to track a set of possible rules.
	"""
	shift: Dict[str, int]  # symbol => state-id
	reduce: Set[int]  # rule-id
	def reductions_before(self, lexeme): return self.reduce


def lr0_construction(grammar:context_free.ContextFreeGrammar) -> HFA[LR0_State]:
	"""
	In broad strokes, this is a subset-construction with a sophisticated means
	to identify successor-states. The keys (by which nodes are identified) are
	core-sets of LR0 parse items, themselves pairs of (rule-id, position).
	
	Additionally, during the full-elaboration step in visiting a core, completed
	parse-items correspond to a state's `reduce` entries. We don't worry about
	look-ahead in this construction: hence the '0' in LR(0). The net result is
	a compact table generated very quickly, but with somewhat limited power.
	In practical systems, LR(0) is normally just a first step, but some few
	grammars are deterministic in LR(0).
	"""
	
	def build_state(core: frozenset):
		step, reduce = collections.defaultdict(set), set()
		def visit(item):
			rule_id, position = item
			if position < len(RHS[rule_id]):
				next_symbol = RHS[rule_id][position]
				step[next_symbol].add((rule_id,position+1))
				return symbol_front.get(next_symbol)
			elif rule_id<len(grammar.rules): reduce.add(rule_id)
		foundation.transitive_closure(core, visit)
		graph.append(LR0_State(shift=ure.find_shifts(step), reduce=reduce, ))
	
	assert grammar.start
	##### Arranging certain bits of the grammar data in a convenient form:
	RHS = [rule.rhs for rule in grammar.rules] # This soon gets augmented internal to this algorithm.
	def front(rule_ids): return frozenset([(r,0) for r in rule_ids])
	symbol_front = {symbol: front(rule_ids) for symbol, rule_ids in grammar.symbol_rule_ids.items()}
	bft = foundation.BreadthFirstTraversal()
	ure = UnitReductionEliminator(grammar, bft)
	graph = []
	# Initial-state cores refer only to the "augmentation" rule -- which has no LHS in this manifestation.
	initial = [bft.lookup(front([foundation.allocate(RHS, [language])])) for language in grammar.start]
	bft.execute(build_state)
	accept = [graph[qi].shift[language] for qi, language in zip(initial, grammar.start)]
	return HFA(graph=graph, initial=initial, accept=accept, grammar=grammar, bft=bft)


class UnitReductionEliminator:
	def __init__(self, grammar:context_free.ContextFreeGrammar, bft:foundation.BreadthFirstTraversal):
		self.bft = bft
		self.unit_rules = {}
		self.eligible_rhs = set()
		for rule_id, rule in enumerate(grammar.rules):
			if rule.attribute is None and len(rule.rhs) == 1:
				self.unit_rules[rule_id] = rule.lhs
				self.eligible_rhs.add(rule.rhs[0])

	def find_shifts(self, step: dict) -> dict:
		"""
		A unit-rule is eligible to be elided (optimized-to-nothing) exactly when
		the state reached by shifting the RHS would have no parse items associated with
		any other rule. Naively, we'd shift the RHS and then immediately back out and
		reduce to the LHS. We prefer to avoid pointless dancing about in the final automaton,
		so we detect the situation and correct for it by redirecting the RHS as if we were
		shifting the LHS instead, essentially running the reduction at table-generation time
		before a numbered state ever gets allocated.
		
		There are TWO little caveats:
		
		The target state, after traversing a unit rule, may or may not contain a reduction
		for that rule: this creates a slightly un-intuitive situation for the LALR construction.
		
		LR(1) and IE-LR(1) need to be able to find "iso-cores", so they must ALSO use this
		to avoid accidentally trying to find an iso-core that doesn't exist in the corresponding
		LR(0) automaton they use as an initial step.
		"""
		replace = {}
		for symbol in self.eligible_rhs & step.keys():
			each_item = iter(step[symbol])
			rule_id = next(each_item)[0]
			if rule_id in self.unit_rules and all(item[0] == rule_id for item in each_item):
				replace[symbol] = self.unit_rules[rule_id]
		shifts = {}
		for symbol in step.keys():
			proxy = symbol
			while proxy in replace: proxy = replace[proxy]
			shifts[symbol] = self.bft.lookup(frozenset(step[proxy]), breadcrumb=proxy)
		return shifts


class LA_State(NamedTuple):
	"""
	The key difference here from LR(0) is that the possible reductions are keyed
	to lookahead tokens from the follow-set of that reduction *however derived*.
	"""
	shift: Dict[str, int]
	reduce: Dict[str, List[int]]
	def reductions_before(self, lexeme): return self.reduce.get(lexeme, ())


def lalr_construction(grammar:context_free.ContextFreeGrammar) -> HFA[LA_State]:
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
	
	glr0 = lr0_construction(grammar)
	terminals = grammar.apparent_terminals()
	token_sets = [terminals.intersection(node.shift.keys()) for node in glr0.graph]
	for q in glr0.accept: token_sets[q].add(END) # Denoting that end-of-input can follow a sentence.
	# Allocate and track/label all follow sets:
	follow = {}
	for q, node in enumerate(glr0.graph):
		for rule_id in node.reduce:
			follow[q,rule_id] = foundation.allocate(token_sets, set())
	# Generate a token-set inflow graph with nodes as lists of inbound edges.
	inflow:List[Set[int]] = [set() for _ in token_sets]
	for q, node in enumerate(glr0.graph):
		for symbol, target in node.shift.items():
			if symbol in grammar.symbol_rule_ids: # That is, if symbol is non-terminal,
				for rule_id in grammar.symbol_rule_ids[symbol]:
					rule_end = glr0.traverse(q, grammar.rules[rule_id].rhs)
					if (rule_end, rule_id) in follow: # Otherwise a unit-reduction was elided here.
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
	def transmogrify(q:int, node:LR0_State) -> LA_State:
		""" This doesn't worry about precedence declarations just yet... """
		reduce = {}
		for rule_id in node.reduce:
			for token in token_sets[follow[q, rule_id]]:
				assert isinstance(token, str)
				if token not in reduce: reduce[token] = [rule_id]
				else: reduce[token].append(rule_id) # This branch represents an R/R conflict...
		return LA_State(node.shift, reduce)
	return HFA(
		graph=[transmogrify(q, node) for q, node in enumerate(glr0.graph)],
		initial=glr0.initial, accept=glr0.accept, grammar=grammar, bft=glr0.bft
	)

def canonical_lr1(grammar:context_free.ContextFreeGrammar) -> HFA[LA_State]:
	"""
	Before embarking on a quest to produce a minimal-LR(1) table by sophisticated
	methods, it's worth learning how to produce the maximal-LR(1) table by (some
	variant of) Knuth's original method.
	
	A Knuth parse-item is like an LR(0) item augmented with the (1) next token
	expected AFTER the corresponding rule would be recognized. The initial core
	would look like { .S/# } in the usual notation. Otherwise, the algorithm has
	much in common with the LR(0) construction above.
	"""
	
	lr0 = lr0_construction(grammar) # This implicitly solves a lot of sub-problems.
	first, epsilon = grammar.find_first_and_epsilon()
	terminals = grammar.apparent_terminals()
	def transparent(symbols): return all(s in epsilon for s in symbols)
	def build_state(core: frozenset):
		isocore = frozenset((r,p) for (r,p,f) in core)
		isostate = lr0.graph[lr0.bft.catalog[isocore]]
		
		step, reduce = collections.defaultdict(set), collections.defaultdict(list)
		def visit(item):
			rule_id, position, follow = item
			rhs = RHS[rule_id]
			if position < len(rhs):
				next_symbol = rhs[position]
				step[next_symbol].add((rule_id, position+1, follow))
				after = set(lr0.graph[isostate.shift[next_symbol]].shift.keys()) & terminals
				if transparent(rhs[position+1:]): after.add(follow)
				if next_symbol in grammar.symbol_rule_ids: return front(grammar.symbol_rule_ids[next_symbol], after )
			elif rule_id<len(grammar.rules): reduce[follow].append(rule_id)
		foundation.transitive_closure(core, visit)
		graph.append(LA_State(shift=ure.find_shifts(step), reduce=reduce,))
	
	assert grammar.start
	RHS = [rule.rhs for rule in grammar.rules]
	graph = []
	# Initial-state cores refer only to the "augmentation" rule -- which has no LHS in this manifestation.
	def front(rule_ids, follow): return frozenset([(r,0, s) for r in rule_ids for s in follow])
	bft = foundation.BreadthFirstTraversal()
	ure = UnitReductionEliminator(grammar, bft)
	graph = []
	initial = [bft.lookup(front([foundation.allocate(RHS, [language])], [END])) for language in grammar.start]
	bft.execute(build_state)
	accept = [graph[qi].shift[language] for qi, language in zip(initial, grammar.start)]
	print("LR(0) states: %d\t\tLR(1) states:%d" % (len(lr0.graph), len(graph)))
	return HFA(graph=graph, initial=initial, accept=accept, grammar=grammar, bft=bft)

PARSE_TABLE_METHODS = {
	'LALR': lalr_construction,
	'CLR': canonical_lr1,
}

DEFAULT_TABLE_METHOD = 'LALR'


