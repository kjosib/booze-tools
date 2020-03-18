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
import collections, sys
from typing import NamedTuple, Iterable, TypeVar, Generic, List, Dict, Set, Tuple
from ..support import foundation, pretty, interfaces
from . import context_free

T = TypeVar('T')

class PurityError(ValueError):
	""" Raised if a grammar has the wrong/undeclared conflicts. """

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
	
	def earley_core(self, q:int):
		""" Maybe we need to know the core-items that a state began from, stripped of look-ahead powers. """
		return sorted(set((r,p) for r, p, *_ in self.bft.traversal[q]))
	
	def traverse(self, q: int, symbols:Iterable) -> int:
		""" Starting in state q, follow the shifts for symbols, and return the resulting state ID. """
		for s in symbols: q = self.graph[q].shift[s]
		return q
	
	def make_dot_file(self, path):
		""" Make a file suitable for the "dot" application from the Graphviz package. """
		with open(path, 'w') as fh:
			fh.write("digraph {\n")
			for q, state in enumerate(self.graph):
				sym = self.bft.breadcrumbs[q] or ''
				sym = sym.replace('"', r'\"')
				if sym.endswith('\\'): sym = sym + ' '
				fh.write("%d [label=\"%d: %s\"]\n"%(q, q, sym))
				for i in state.shift.values():
					fh.write("\t%d -> %d\n"%(q,i))
			fh.write('}\n')
		pass
	
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
			if not alive: raise interfaces.GeneralizedParseError("Parser died midway at something ungrammatical.")
		for stack in alive:
			q = stack[0]
			if q == accept: return True
			for rule_id in self.graph[q].reductions_before(interfaces.END_OF_TOKENS):
				alive.append(reduce(stack, rule_id))
		raise interfaces.GeneralizedParseError("Parser recognized a viable prefix, but not a complete sentence.")

class LR0_State(NamedTuple):
	"""
	The LR(0) construction completely ignores look-ahead for reduce-rules, so for a
	non-deterministic parse table, it's enough to track a set of possible rules.
	"""
	shift: Dict[str, int]  # symbol => state-id
	reduce: Set[int]  # rule-id
	def reductions_before(self, lexeme): return self.reduce


def lr0_construction(grammar: context_free.ContextFreeGrammar) -> HFA[LR0_State]:
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
	RHS = grammar.augmented_rules()
	def front(rule_ids): return frozenset([(r,0) for r in rule_ids])
	symbol_front = {symbol: front(rule_ids) for symbol, rule_ids in grammar.symbol_rule_ids.items()}
	bft = foundation.BreadthFirstTraversal()
	ure = UnitReductionEliminator(grammar, bft)
	graph = []
	initial = [bft.lookup(front([rule_id])) for rule_id in grammar.initial()]
	bft.execute(build_state)
	accept = [graph[qi].shift[language] for qi, language in zip(initial, grammar.start)]
	return HFA(graph=graph, initial=initial, accept=accept, grammar=grammar, bft=bft)


class UnitReductionEliminator:
	def __init__(self, grammar: context_free.ContextFreeGrammar, bft: foundation.BreadthFirstTraversal):
		self.bft = bft
		self.unit_rules = {}
		self.eligible_rhs = set()
		for rule_id, rule in enumerate(grammar.rules):
			if rule.is_rename():
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


def lalr_construction(grammar: context_free.ContextFreeGrammar) -> HFA[LA_State]:
	"""
	Building a non-deterministic LALR(1)-style table is a direct extension of the LR(0)
	construction. LR(0) tables tend to have lots of inadequate states. If we figure out
	which look-ahead tokens are relevant to which reductions, then the automaton gets a
	good deal more capable. In the limit, there is canonical LR(1) as given by Knuth.
	That's traditionally been considered impractical for all but the very smallest
	grammars. Today's workstations have the chops to handle canonical LR(1) even for
	larger grammars, but it's still a chore and, as we will see, a needless one.
	
	The bulk of the work involved consists of finding the follow-sets for reductions.
	I've chosen to break that work into its own function, rather than code the entire
	LALR construction as one function, for two reasons. First, it's an interesting
	algorithm in its own right. Second, that function provides the perfect level of
	abstraction for exploitation later in the minimal-LR(1) construction given later.
	
	If we stop here, we get a table that's more efficient than LR(0) for generalized
	parsing: it will attempt many fewer dead-end reductions before look-ahead tokens
	that LALR determines not to be in the reduction's follow-set.
	"""
	lr0 = lr0_construction(grammar)
	token_sets, follow = lalr_first_and_follow(lr0)
	def make_lalr_state(q:int, node:LR0_State) -> LA_State:
		reduce = {}
		for rule_id in node.reduce:
			for token in token_sets[follow[q, rule_id]]:
				assert isinstance(token, str)
				if token not in reduce: reduce[token] = [rule_id]
				else: reduce[token].append(rule_id) # This branch represents an R/R conflict...
		# At this point, `LA_State(node.shift, reduce)` would be a nice, potentially
		# non-deterministic HFA state incorporating information about LALR follow sets.
		# We can do better: Calling upon the "reachable" function causes the resulting
		# non-deterministic HFA to respect precedence and associativity (P&A) declarations.
		# This parallels the corresponding call in the true-LR(1) algorithm, simplifies
		# the construction of a deterministic table, does not change the deterministic
		# semantics, and may have some subtle implications for GLR semantics in the presence
		# of P&A declarations. In particular, an invasive high-precedence reduction could
		# cause trouble. I've not taken the time to work out if that's even a thing, though.
		# For now, if you want to do GLR parsing, use the minimal_lr1(...) construction.
		step = reachable(node.shift, reduce, grammar)
		# Having done that, it's entirely plausible that some unreachable states may
		# exist. It's probably not worth worrying about.
		return LA_State(step, reduce)
	return HFA(
		graph=[make_lalr_state(q, node) for q, node in enumerate(lr0.graph)],
		initial=lr0.initial, accept=lr0.accept, grammar=grammar, bft=lr0.bft
	)

def lalr_first_and_follow(lr0:HFA[LR0_State]) -> Tuple[list, dict]:
	"""
	This is a variant of the channel algorithm as described (colorfully and frankly not
	very clearly) in chapter 9 of Parsing Techniques: a Practical Guide, by Dick Grune
	and Ceriel Jacobs. In essence the idea is to build a directed graph by certain rules
	and then "flow" terminal symbols around the nodes in that graph until updates cease.
	You may recognize this as a fix-point over the set-union operation. It turns out we
	can do better: using Tarjan's Strongly-Connected-Components algorithm and orienting
	the edges in the correct direction, we need only ever consider each edge once.
	"""
	grammar = lr0.grammar
	terminals = grammar.apparent_terminals()
	token_sets = [terminals.intersection(node.shift.keys()) for node in lr0.graph]
	for q in lr0.accept:
		token_sets[q].add(interfaces.END_OF_TOKENS) # Denoting that end-of-input can follow a sentence.
	# Allocate and track/label all follow sets:
	follow = {}
	for q, node in enumerate(lr0.graph):
		for rule_id in node.reduce:
			follow[q,rule_id] = foundation.allocate(token_sets, set())
	# Generate a token-set inflow graph with nodes as lists of inbound edges.
	inflow:List[Set[int]] = [set() for _ in token_sets]
	for q, node in enumerate(lr0.graph):
		for symbol, target in node.shift.items():
			if symbol in grammar.symbol_rule_ids: # That is, if symbol is non-terminal,
				for rule_id in grammar.symbol_rule_ids[symbol]:
					rule_end = lr0.traverse(q, grammar.rules[rule_id].rhs)
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
	return token_sets, follow

def canonical_lr1(grammar: context_free.ContextFreeGrammar) -> HFA[LA_State]:
	"""
	Before embarking on a quest to produce a minimal-LR(1) table by sophisticated
	methods, it's worth learning how to produce the maximal-LR(1) table by (some
	variant of) Donald E. Knuth's original method.

	A Knuth parse-item is like an LR(0) item augmented with the (1) next token
	expected AFTER the corresponding rule would be recognized. The initial core
	would look like { .S/# } in the usual notation. Otherwise, the algorithm has
	much in common with the LR(0) construction above -- but to see that clearly
	you'll have to look at the function `abstract_lr1_construction(...)`.
	"""
	
	def front(symbol, follower, goto_transparent, iso_q):
		"""
		Return the list of parse-items which DIRECTLY follow from the given criteria.
		In Canonical LR(1), that means the beginnings of each rule for the
		prediction-symbol, with followers being every terminal that might come
		next after the prediction-symbol got shifted.
		"""
		iso_state = lr0.graph[iso_q]
		goto_state = lr0.graph[iso_state.shift[symbol]]
		after = set(goto_state.shift.keys()) & terminals
		if goto_transparent: after.add(follower)
		items = []
		for rule_id in grammar.symbol_rule_ids[symbol]:
			items.extend((rule_id, 0, lookahead) for lookahead in after)
		return items
	
	lr0 = lr0_construction(grammar) # This implicitly solves a lot of sub-problems.
	terminals = grammar.apparent_terminals()
	return abstract_lr1_construction(
		grammar, front = front,
		note_reduce = lambda reduce, follower, rule_id, iso_q: reduce[follower].append(rule_id),
		initial_item = lambda rule_id: (rule_id, 0, interfaces.END_OF_TOKENS),
		lr0_catalog=lr0.bft.catalog,
	)

def abstract_lr1_construction(
		grammar: context_free.ContextFreeGrammar, *,
		front, note_reduce, initial_item, lr0_catalog,
) -> HFA[LA_State]:
	"""
	The Canonical and Minimal LR(1) algorithms given here have a great deal in common.
	It seems both instructive and useful to factor out those commonalities.
	If you stare intently, you'll also see similarity to LR(0), but factoring
	out that particular commonality is not today's exercise.
	"""
	def build_state(core: frozenset):
		iso_q = lr0_catalog[frozenset((r, p) for (r, p, f) in core)]
		step, reduce = collections.defaultdict(set), collections.defaultdict(list)
		def visit(item):
			rule_id, position, follower = item
			rhs = RHS[rule_id]
			if position < len(rhs): # We have a non-terminal.
				next_symbol = rhs[position]
				step[next_symbol].add((rule_id, position+1, follower))
				if next_symbol in grammar.symbol_rule_ids:
					return front(next_symbol, follower, transparent(rule_id, position + 1), iso_q)
			elif rule_id<len(grammar.rules): note_reduce(reduce, follower, rule_id, iso_q)
		foundation.transitive_closure(core, visit)
		graph.append(LA_State(shift=ure.find_shifts(reachable(step, reduce, grammar)), reduce=reduce,))
	
	RHS = grammar.augmented_rules()
	transparent = find_transparent(grammar.find_first_and_epsilon()[1], RHS)
	bft = foundation.BreadthFirstTraversal()
	ure = UnitReductionEliminator(grammar, bft)
	graph = []
	initial = [bft.lookup(frozenset([initial_item(rule_id)])) for rule_id in grammar.initial()]
	bft.execute(build_state)
	accept = [graph[qi].shift[language] for qi, language in zip(initial, grammar.start)]
	# print("LR(0) states: %d\t\tLR(1) states:%d" % (len(lr0_catalog), len(graph)))
	return HFA(graph=graph, initial=initial, accept=accept, grammar=grammar, bft=bft)


def find_transparent(epsilon:Set[str], right_hand_sides:List[List[str]]):
	"""
	In LR(1)-family algorithms, we do a fair amount of tests for the rest-of-a-rule
	being transparent: i.e. all the remaining symbols in a right-hand-side (if any)
	being possibly-epsilon. The naive way -- something like
			all(symbol in epsilon for symbol in rhs[position:])
	works just fine, but think of the all those garbage list copies!
	We can do better. This is one way.
	"""
	def transparency_threshold(rhs):
		position = len(rhs)
		# Invariant: all(symbol in epsilon for symbol in rhs[position:])
		while position > 0 and rhs[position-1] in epsilon: position -= 1
		return position
	thresholds = list(map(transparency_threshold, right_hand_sides))
	return lambda rule_id, position: thresholds[rule_id] <= position


def minimal_lr1(grammar: context_free.ContextFreeGrammar) -> HFA[LA_State]:
	"""
	This amounts to a hybrid of LALR and Canonical LR(1) in which only the conflicted
	parts are reconsidered in greater detail. Details of the approach are in the
	doc-comments for the `front` and `note_reduce` subroutines.
	
	After poring over the IELR paper on several occasions, I believe there may yet be
	some originality in this contribution. If anything, I have an argument why this
	routine produces absolutely minimal tables: each output state has an absolutely
	minimal set of "siblings" affiliated with a corresponding LALR state, because the
	only thing distinguishing "siblings" is the correct final deterministic parse
	action after the rule associated with a parse-item is recognized, and then only
	for those (generally very few) tokens for which LALR does not figure it out. Also,
	unit rule elimination is applied, and unreachable states (in light of conflict
	resolutions) are never considered.
	"""
	def front(symbol, follower, goto_transparent, iso_q):
		"""
		Return the list of parse-items which DIRECTLY follow from the given criteria.
		
		The complexity here comes from how this algorithm threads the needle between
		LALR-when-adequate and LR(1)-when-necessary.
		"""
		isostate = lr0.graph[iso_q]
		items = []
		goto_q = isostate.shift[symbol]
		goto_shifts = lr0.graph[goto_q].shift.keys()
		goto_conflict = conflict_data[goto_q].tokens.keys()
		for sub_rule_id in grammar.symbol_rule_ids[symbol]:
			# Most of the smarts in this algorithm comes down to understanding what
			# LALR found at the far end of each sub-production. We need to know which
			# LR(0) state you reach after shifting the contents of that sub-rule:
			reach = lr0.traverse(iso_q, grammar.rules[sub_rule_id].rhs)
			if follower is None:  # We're coming from LALR-land:
				items.append((sub_rule_id, 0, None))
				reach_conflict = conflict_data[reach].rules.get(sub_rule_id, EMPTY)
				for token in reach_conflict & goto_shifts - goto_conflict:
					# NB: It's tempting to exclude candidate follower-tokens for which
					# a shift is assured according to the precedence declarations, but
					# it doesn't buy you anything (S/R conflicts get resolved later)
					# and in practice it results in larger parse tables.
					# We leave out the "GOTO-conflicted" tokens here because...
					items.append((sub_rule_id, 0, token)) # Canonical parse-item
			else:  # The canonical branch:
				# GOTO-conflicted tokens will have resulted in canonical-style parse items.
				# As with Canonical, they can follow a derivation only when the remainder
				# of the current rule is "transparent", but this algorithm imposes the
				# additional constraint regarding the token's contribution to a
				# LALR-inadequacy in the "reach" state.
				if follower in conflict_data[reach].tokens and goto_transparent:
					assert follower in goto_conflict
					items.append((sub_rule_id, 0, follower))
		return items
	
	def note_reduce(reduce, follower, rule_id, iso_q):
		"""
		There are two cases:
		
		If the "follower" is `None`, it stands for the un-conflicted portion of the
		corresponding LALR follow set.
		
		Otherwise, the token MUST have earlier been implicated in a LALR-inadequacy
		in this state (which fact we assert for good measure). Handle it the same as
		Canonical-LR(1).
		
		Incidentally, it is possible to reach a particular `reduce[follower]` list
		more than once if and only if the follower is LALR-inadequate. Proof follows
		from the fact that a given parse-item is visited at most once.
		"""
		if follower is None:
			for t in token_sets[follow[iso_q, rule_id]] - conflict_data[iso_q].rules[rule_id]:
				assert t not in reduce
				reduce[t] = [rule_id]
		else:
			assert follower in conflict_data[iso_q].rules[rule_id]
			if follower in reduce:
				assert rule_id not in reduce[follower]
				reduce[follower].append(rule_id)
			else: reduce[follower] = [rule_id]
	
	EMPTY = frozenset()
	lr0 = lr0_construction(grammar) # This implicitly solves a lot of sub-problems.
	token_sets, follow = lalr_first_and_follow(lr0)
	# Later we need to know if a certain rule is implicated in an LALR conflict: if so, for which terminals?
	# We also need to know if a state is conflicted with respect to a particular terminal.
	conflict_data = find_conflicts(lr0.graph, {(q,r):token_sets[i] for (q,r),i in follow.items()}, grammar)

	return abstract_lr1_construction(
		grammar,
		front = front, note_reduce = note_reduce,
		initial_item = lambda rule_id: (rule_id, 0, None),
		lr0_catalog=lr0.bft.catalog,
	)

def reachable(step:dict, reduce:dict, grammar) -> dict:
	"""
	The object of this function is to prevent the exploration of useless/unreachable states.
	It does this by deleting a shift from the "step" dictionary whenever said shift becomes
	impossible by virtue of P&A declarations. It also deletes useless reductions similarly
	rendered unavailable, and denotes non-associativity errors by a sentinel empty-tuple.
	
	This was developed to help minimal-LR1 mode respect precedence/associativity, but it's
	equally useful for all modes.
	
	NOTE: When shift/reduce/reduce conflicts arise in connection with operator-precedence
	specifications, the intended semantics for a generalized parse are not always clearly
	defined. The code below should either behave sensibly or toss an exception.
	
	The problem with the bizarre corner cases is they cannot be understood solely in terms
	of actions the parser might (or might not) take in this state. If they come up, you
	get a warning printed on STDERR but otherwise the operator-precedence declarations
	are ignored in that instance.
	"""
	for token, rule_id_list in list(reduce.items()):
		if token not in step: continue
		decide = [grammar.decide_shift_reduce(token, rule_id) for rule_id in rule_id_list]
		ways = set(decide)
		assert context_free.BOGUS not in ways, "This is guaranteed by grammar.validate(...), called earlier."
		if len(ways) == 1:
			decision = ways.pop()
			if decision == context_free.LEFT: del step[token]
			elif decision == context_free.RIGHT: del reduce[token]
			elif decision == context_free.NONASSOC:
				del step[token]
				reduce[token] = ()
			else: assert decision is None
		elif ways == {context_free.LEFT, context_free.NONASSOC}:
			del step[token]
			reduce[token] = tuple(r for r,d in zip(rule_id_list, decide) if d == context_free.LEFT)
		elif ways == {context_free.RIGHT, None}:
			reduce[token] = tuple(r for r, d in zip(rule_id_list, decide) if d != context_free.RIGHT)
		else:
			print("Fair Warning:", token, "triggers a bizarre operator-precedence corner case.", file=sys.stderr)
	return step


class ConflictData(NamedTuple):
	tokens: Dict[str, Set[int]] # The rules that conflict on this token
	rules: Dict[int, Set[str]] # The tokens that conflict on this rule.

def find_conflicts(graph, follow_sets, grammar) -> List[ConflictData]:
	"""
	This drives one of the central ideas of the Minimal-LR(1) algorithm:
	Learn which tokens are involved in conflicts, and which rules contribute
	to those conflicts for each token (as known to LALR).
	
	Subtleties:
	
	1. If an S/R conflict is DECLARED to shift, then it does not impugn the token,
	   but the token still refers to the rule in case some other rule MAY reduce.
	
	This routine (and the stuff that uses it) is coded with the idea that the
	grammar may leave certain things deliberately non-deterministic. Wherever that
	is the case, these algorithms will respect it.
	
	2. There is a way to improve the treatment of R/R conflicts if it is known in
	   advance that the table will be used deterministically, or if the R/R is
	   resolved by rule precedence. It involves a pass over the LR(1) item cores
	   considering the groups that eventually lead to a R/R conflict (they have the
	   same suffix and follower): among those groups only the "winning" reduction
	   item needs to stay in the core. This "normalizes" the LR(1) cores so that
	   potentially fewer distinct ones might be generated.
	
	Alas, idea #2 is not yet implemented. Complex R/R conflicts may still lead to
	more states than strictly necessary for a deterministic table. In practice,
	this is unlikely to be a real problem: deterministic tables are usually made
	from grammars with few LALR conflicts, and in the non-deterministic case
	nothing is wasted. Nevertheless, this remains an avenue for improvement.
	"""
	result = []
	for q, state in enumerate(graph):
		degree = collections.Counter(state.shift.keys()) # This picks up some nonterminals but they do no harm.
		for rule_id in state.reduce:
			for token in follow_sets[q,rule_id]:
				prefer_shift = token in state.shift and grammar.decide_shift_reduce(token, rule_id) == context_free.RIGHT
				if not prefer_shift: degree[token] += 1
		conflicted_tokens = set(token for token, count in degree.items() if count > 1)
		conflict = ConflictData({token: set() for token in conflicted_tokens}, {})
		for rule_id in state.reduce:
			contribution = conflicted_tokens & follow_sets[q,rule_id]
			conflict.rules[rule_id] = contribution
			for token in contribution: conflict.tokens[token].add(rule_id)
		result.append(conflict)
	return result


class DragonBookTable(interfaces.ParseTable):
	"""
	This is the classic textbook view of a set of parse tables: a pair of dense matrices
	(implemented here as lists-of-lists) representing the "ACTION" and "GOTO" tables, along
	with information about the reduction rules. The contents of these matrices are just
	numbers representing parse actions.
	
	This is a reasonable implementation as-is if you have a modern amount of RAM in your
	machine. In days of old, it would be necessary to compress the parse tables. Today,
	that's still not such a bad idea if you can pre-compute the tables. The compaction
	submodule contains some code for a typical method of parser table compression, and
	the runtime submodule implements the ParseTable interface atop a compressed table.
	
	Design note: There's a temptation to make the constructor take an HFA object, but
	that limits the ways you can instantiate this class. See the function `tabulate(...)`.
	"""
	
	def __init__(self, *, initial: dict, action: list, goto: list, essential_errors: set, rules: list, terminals: list,
	             nonterminals: list, breadcrumbs: list, splits=()):
		self.initial = initial
		self.action_matrix = action
		self.goto_matrix = goto
		self.essential_errors = essential_errors
		self.translate = {symbol: i for i, symbol in enumerate(terminals)}
		nontranslate = {symbol: i for i, symbol in enumerate(nonterminals)}
		self.terminals, self.nonterminals = terminals, nonterminals
		self.breadcrumbs = breadcrumbs
		self.constructors = [None, *(set(rule.constructor for rule in rules) - {None})]
		ctrans = {c:i for i,c in enumerate(self.constructors)}
		def translate_rule(rule:context_free.Rule):
			size = len(rule.rhs)
			if isinstance(rule.places, int):
				assert rule.constructor is None
				c,p = rule.places-size, ()
			else: c,p = ctrans[rule.constructor], tuple(x-size for x in rule.places)
			return nontranslate[rule.lhs], size, c, p
		self.rule_table = list(map(translate_rule, rules))
		self.rule_origin = [rule.origin for rule in rules]
		self.splits = splits # A non-deterministic table just needs one extra bit: this list of lists.
		
		interactive = []
		for row in action:
			k = set(row)
			k.discard(0)
			if len(k) == 1: interactive.append(min(k.pop(), 0))
			else: interactive.append(0)
		for q, t in essential_errors: interactive[q] = False
		self.interactive_step = self.interactive_rule_for = interactive.__getitem__
	
	def get_rule(self, rule_id: int) -> tuple:
		return self.rule_table[rule_id]
	
	def get_translation(self, symbol) -> int:
		try: return self.translate[symbol]
		except KeyError: return len(self.terminals) # Guaranteed to trigger error-processing.
		
	def get_action(self, state_id, terminal_id) -> int: return self.action_matrix[state_id][terminal_id]
	
	def get_goto(self, state_id, nonterminal_id) -> int: return self.goto_matrix[state_id][nonterminal_id]
	
	def get_initial(self, language) -> int: return 0 if language is None else self.initial[language]
	
	def get_breadcrumb(self, state_id) -> str: return self.breadcrumbs[state_id]
	
	def display(self):
		size = len(self.action_matrix)
		print('Action and Goto: (%d states)' % size)
		head = ['', ''] + self.terminals + [''] + self.nonterminals
		body = []
		for i, (b, a, g) in enumerate(zip(self.breadcrumbs, self.action_matrix, self.goto_matrix)):
			body.append([i, b, *a, '', *g])
		pretty.print_grid([head] + body)
	
	def make_csv(self, pathstem):
		""" Generate action and goto tables into CSV files suitable for inspection in a spreadsheet program. """
		
		def mask(q, row, essential):
			return [
				s if s or (q, t) in essential else None
				for t, s in enumerate(row)
			]
		
		def typical_grid(top, matrix, essential):
			head = [None, None, *top]
			return [head] + [[q, self.breadcrumbs[q]] + mask(q, row, essential) for q, row in enumerate(matrix)]
		
		pretty.write_csv_grid(pathstem + '.action.csv',
			typical_grid(self.terminals, self.action_matrix, self.essential_errors))
		pretty.write_csv_grid(pathstem + '.goto.csv', typical_grid(self.nonterminals, self.goto_matrix, frozenset()))
	
	def get_split_offset(self) -> int:
		return len(self.action_matrix)
	
	def get_split(self, split_id: int) -> list:
		assert split_id>0
		return self.splits[split_id]




class ParsingStyle:
	"""
	There are three main ways to deal with inadequacies (non-determinism) remaining
	after application of any P&A declarations:
		1. Pure: Inadequacies are considered a grammar bug.
		2. Deterministic: Inadequacies are resolved to shift, or to use the earliest-defined rule.
		3. Generalized: Inadequacies are converted to parser-split entries.
	
	Probably the correct choice of style should be reflected in the grammar definition somehow.
	"""
	
	def decide_inadequacy(self, q:int, look_ahead:str, shift:int, rule_ids:Iterable, rules:list) -> int:
		""" Called in all non-deterministic situations. """
		raise NotImplementedError(type(self))
	
	def any_splits(self):
		""" Return nothing, or a list of splits for use in non-deterministic parsing algorithms. """
		raise NotImplementedError(type(self))

	def report(self, hfa):
		""" Give user-feedback about any observed challenges. """
		raise NotImplementedError(type(self))

class DeterministicStyle(ParsingStyle):
	
	def __init__(self, strict:bool):
		self.conflicts = collections.defaultdict(list)
		self.strict = strict
	
	def decide_inadequacy(self, q:int, look_ahead: str, shift: int, rule_ids: Iterable, rules:list) -> int:
		self.conflicts[q, look_ahead].extend(rule_ids)
		return shift or encode_reduce(min(rule_ids))
	
	def any_splits(self):
		pass
	
	def report(self, hfa):
		"""
		This function was originally intended as a way to visualize the branches of a conflict.
		In its original form a bunch of context was available; I've gratuitously stripped that away
		and now I want to break this down to the bits we actually need.
		
		BreadthFirstTraversal.traversal[x] was used to grab the core parse items in order to
		visualize the state reached by shifting the lookahead token if that shift is viable.
		Such really belongs as a method on the state: soon it will move there.
		
		The "options" list contains numeric candidate ACTION instructions which are interpreted
		in the usual way: This does represent a data-coupling, but one that's unlikely to change,
		so I'm not too worried about it just now.
		
		In conclusion: Let the objects defined in automata.py format parse-states for human consumption.
		"""
		for (q, lookahead), rule_ids in sorted(self.conflicts.items()):
			hfa.display_situation(q, lookahead)
			if lookahead in hfa.graph[q]:
				shift = hfa.graph[q][lookahead]
				print("Do we shift into:")
				left_parts, right_parts = [], []
				for r, p in hfa.earley_core(shift):
					rhs = hfa.grammar.rules[r].rhs
					left_parts.append(' '.join(rhs[:p]))
					right_parts.append(' '.join(rhs[p:]))
				align = max(map(len, left_parts)) + 10
				for l, r in zip(left_parts, right_parts):
					print(' ' * (align - len(l)) + l + '  ' + pretty.DOT + '  ' + r)
			for r in rule_ids:
				rule = hfa.grammar.rules[r]
				print("Do we reduce:  %s -> %s" % (rule.lhs, ' '.join(rule.rhs)))
		if self.strict and self.conflicts: raise PurityError()


class GeneralizedStyle(ParsingStyle):
	
	def __init__(self, splits_offset:int, nondeterministic_symbols:set):
		self.offset = splits_offset
		self.splits = []
		self.nondeterministic_symbols = nondeterministic_symbols
	
	def decide_inadequacy(self, q: int, look_ahead: str, shift: int, rule_ids: Iterable, rules:list) -> int:
		split = []
		if shift: split.append(shift)
		for r in sorted(rule_ids, key=lambda i:len(rules[i].rhs)): split.append(-1-r)
		return self.offset + foundation.allocate(self.splits, split)
	
	def any_splits(self):
		return self.splits
	
	def report(self, hfa):
		print(len(self.splits), "non-deterministic situation(s) encountered.")


def encode_reduce(rule_id:int) -> int:
	""" See interface.ParseTable.get_action. """
	return -1 - rule_id

def tabulate(hfa: HFA[LA_State], *, style:ParsingStyle) -> DragonBookTable:
	"""
	Having an HFA based on State objects, this function produces a corresponding
	dense-matrix-style parse table of the sort typically shown in textbook descriptions
	of LR-style parsing automata.
	
	This function does NOT worry about precedence and associativity declarations:
	It assumes that concern has already been taken care of in the input HFA -
	principally by the interaction of function `reachable(...)` with the P&A bits.
	
	Any residual inadequacies of the grammar are delegated to the `style` object for
	resolution.
	"""
	grammar = hfa.grammar
	assert interfaces.END_OF_TOKENS not in grammar.symbols
	assert interfaces.ERROR_SYMBOL not in grammar.symbol_rule_ids
	terminals = [interfaces.END_OF_TOKENS] + sorted(grammar.apparent_terminals())
	translate = {t:i for i,t in enumerate(terminals)}
	nonterminals = sorted(grammar.symbol_rule_ids.keys())
	##### Tabulate the states into dense matrices ACTION and GOTO:
	action, goto, essential_errors = [], [], set()
	conflict = collections.defaultdict(set)
	for q, state in enumerate(hfa.graph):
		goto.append([state.shift.get(s, 0) for s in nonterminals])
		action_row = [state.shift.get(s, 0) for s in terminals]
		conflict.clear()
		for symbol, rule_ids in state.reduce.items():
			idx = translate[symbol]
			shift = action_row[idx]
			if rule_ids == ():
				# This is how function `reachable(...)` communicates a non-association situation.
				assert shift == 0
				essential_errors.add((q,idx))
			elif shift == 0 and len(rule_ids) == 1:
				action_row[idx] = encode_reduce(rule_ids[0])
			else: action_row[idx] = style.decide_inadequacy(q, symbol, shift, rule_ids, grammar.rules)
		action.append(action_row)
	for q, t in essential_errors: action[q][t] = 0
	for q in hfa.accept: action[q][0] = q
	style.report(hfa)
	return DragonBookTable(
		initial=dict(zip(grammar.start, hfa.initial)),
		action=action,
		goto=goto,
		essential_errors=essential_errors,
		rules=grammar.rules,
		terminals=terminals,
		nonterminals=nonterminals,
		breadcrumbs=hfa.bft.breadcrumbs,
		splits=style.any_splits()
	)


PARSE_TABLE_METHODS = {
	'LALR': lalr_construction,
	'CLR': canonical_lr1,
	'LR1': minimal_lr1,
}


