from collections import defaultdict, Counter
from typing import NamedTuple
from ..support.foundation import transitive_closure, BreadthFirstTraversal
from .interface import END_OF_TOKENS
from .context_free import ContextFreeGrammar, RIGHT
from .automata import HFA, LookAheadState, reachable
from .lr0 import lr0_construction, ParseItemMap
from .lalr import find_lalr_sets

def canonical_lr1(grammar: ContextFreeGrammar) -> HFA[LookAheadState]:
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
		return [
			(lr0_item, lookahead)
			for lr0_item in pim.symbol_front.get(symbol)
			for lookahead in after
		]
	
	pim = ParseItemMap.from_grammar(grammar)
	lr0 = lr0_construction(pim)  # This implicitly solves a lot of sub-problems.
	terminals = grammar.apparent_terminals()
	return abstract_lr1_construction(
		pim, grammar,
		front=front,
		note_reduce=lambda reduce, follower, rule_id, iso_q: reduce[follower].append(rule_id),
		initial_follow=END_OF_TOKENS,
		lr0_catalog=lr0.bft.catalog,
	)


def abstract_lr1_construction(pim: ParseItemMap, grammar: ContextFreeGrammar, *, front, note_reduce, initial_follow, lr0_catalog) -> HFA[LookAheadState]:
	"""
	The Canonical and Minimal LR(1) algorithms given here have a great deal in common.
	It seems both instructive and useful to factor out those commonalities.
	If you stare intently, you'll also see similarity to LR(0), but factoring
	out that particular commonality is not today's exercise.
	"""
	
	def build_state(lr1_core: frozenset):
		iso_q = lr0_catalog[frozenset(i for (i, f) in lr1_core)]
		shifted_cores, reduce = defaultdict(set), defaultdict(list)
		
		def visit(lr1_item):
			lr0_item, follower = lr1_item
			
			next_symbol = pim.symbol_at[lr0_item]
			if next_symbol is None:
				rule_id = pim.rule_found[lr0_item]
				if rule_id < len(grammar.rules):
					note_reduce(reduce, follower, rule_id, iso_q)
			else:
				shifted_cores[next_symbol].add((lr0_item + 1, follower))
				if next_symbol in grammar.symbol_rule_ids:
					# i.e. next_symbol is a non-terminal:
					return front(next_symbol, follower, transparent[lr0_item + 1], iso_q)
		
		transitive_closure(lr1_core, visit)
		shift = {
			symbol: bft.lookup(frozenset(item_set), breadcrumb=symbol)
			for symbol, item_set in reachable(shifted_cores, reduce, grammar).items()
		}
		graph.append(LookAheadState(shift=shift, reduce=reduce))
	
	transparent = find_transparent(grammar.find_epsilon(), pim.symbol_at)
	bft = BreadthFirstTraversal()
	graph = []
	initial_items = [(i, initial_follow) for i in pim.language_front]
	initial = [bft.lookup(frozenset([item])) for item in initial_items]
	bft.execute(build_state)
	accept = [graph[qi].shift[language] for qi, language in zip(initial, grammar.start)]
	# print("LR(0) states: %d\t\tLR(1) states:%d" % (len(lr0_catalog), len(graph)))
	return HFA(graph=graph, initial=initial, accept=accept, bft=bft)


def find_transparent(epsilon: set[str], symbol_at:list[str]) -> list[bool]:
	"""
	In LR(1)-family algorithms, we do a fair amount of tests for the rest-of-a-rule
	being transparent: i.e. all the remaining symbols in a right-hand-side (if any)
	being possibly-epsilon. The naive way -- something like
			all(symbol in epsilon for symbol in rhs[position:])
	works just fine, but think of the all those garbage list copies!
	We can do better. This is one way.
	"""
	
	flag = False
	transparent = [False] * len(symbol_at)
	for i in reversed(range(len(transparent))):
		if symbol_at[i] is None:
			flag=True
			transparent[i] = flag
		elif symbol_at[i] in epsilon:
			transparent[i] = flag
		else: flag=False
	return transparent


def minimal_lr1(grammar: ContextFreeGrammar) -> HFA[LookAheadState]:
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
		In other words, these will be parse-items in position zero for the rules that
		apply to nonterminal :param symbol:.

		:param follower: may be `None` to mean "the non-conflicted portion of the reduce set,
		or may be a specific reduce-set token.

		:param goto_transparent: means there is an epsilon-only path through any
		remaining portion of the rule :param symbol: appeared in, so that reduce-set
		conflicts should be propagated to these resulting parse-items.

		:param iso_q: is the ID number in the LR(0)/LALR graph corresponding to the
		LR(1) state under construction.

		The complexity here comes from how this algorithm threads the needle between
		LALR-when-adequate and LR(1)-when-necessary.
		"""
		isostate = lr0.graph[iso_q]
		items = []
		goto_q = isostate.shift[symbol]
		goto_conflict = conflict_data[goto_q].tokens.keys()
		for sub_rule_id, lr0_item in zip(grammar.symbol_rule_ids[symbol], pim.symbol_front[symbol]):
			# Most of the smarts in this algorithm comes down to understanding what
			# LALR found at the far end of each sub-production. We need to know which
			# LR(0) state you reach after shifting the contents of that sub-rule.
			# (Incidentally, the LALR construction also discovers this same information.)
			reach = lr0.traverse(iso_q, grammar.rules[sub_rule_id].rhs)
			if follower is None:  # We're coming from LALR-land:
				items.append((lr0_item, None))
				reach_conflict = conflict_data[reach].rules.get(sub_rule_id, EMPTY)
				possible_follow = reach_conflict & successors[goto_q]
				# Things get a bit weird for tokens that are ALSO conflicted in the
				# goto state. Normally, we ignore them in this section; they'll come
				# along expressly in another round through the algorithm as a split
				# from the goto-state. However, in case of epsilon productions we
				# must include those tokens lest the parse table may come out wrong.
				if reach != iso_q: possible_follow -= goto_conflict
				for token in possible_follow: items.append((lr0_item, token))
			else:  # The canonical branch:
				# GOTO-conflicted tokens will have resulted in canonical-style parse items.
				# As with Canonical, they can follow a derivation only when the remainder
				# of the current rule is "transparent", but this algorithm imposes the
				# additional constraint regarding the token's contribution to a
				# LALR-inadequacy in the "reach" state.
				if follower in conflict_data[reach].tokens and goto_transparent:
					assert follower in goto_conflict
					items.append((lr0_item, follower))
		return items
	
	def note_reduce(reduce, follower, rule_id, iso_q):
		"""
		There are two cases:

		If the "follower" is `None`, it stands for the un-conflicted portion of the
		corresponding LALR reduce-set.

		Otherwise, the token MUST have earlier been implicated in a LALR-inadequacy
		in this state (which fact we assert for good measure). Handle it the same as
		Canonical-LR(1).

		Incidentally, it is possible to reach a particular `reduce[follower]` list
		more than once if and only if the follower is LALR-inadequate. Proof follows
		from the fact that a given parse-item is visited at most once.
		"""
		if follower is None:
			for t in terminal_sets[reduce_set_id[iso_q, rule_id]] - conflict_data[iso_q].rules[rule_id]:
				assert t not in reduce
				reduce[t] = [rule_id]
		else:
			assert follower in conflict_data[iso_q].rules[rule_id]
			if follower in reduce:
				assert rule_id not in reduce[follower]
				reduce[follower].append(rule_id)
			else:
				reduce[follower] = [rule_id]
	
	def possible_next_terminals(iso_q):
		union = set(terminal_sets[iso_q])
		for rule_id in lr0.graph[iso_q].reduce:
			union.update(terminal_sets[reduce_set_id[iso_q, rule_id]])
		return union
	
	EMPTY = frozenset()
	pim = ParseItemMap.from_grammar(grammar)
	lr0 = lr0_construction(pim)  # This implicitly solves a lot of sub-problems.
	terminal_sets, reduce_set_id = find_lalr_sets(lr0, grammar)
	successors = [possible_next_terminals(iso_q) for iso_q in range(len(lr0.graph))]
	# Later we need to know if a certain rule is implicated in an LALR conflict: if so, for which terminals?
	# We also need to know if a state is conflicted with respect to a particular terminal.
	conflict_data = find_conflicts(lr0.graph, {(q, r): terminal_sets[i] for (q, r), i in reduce_set_id.items()}, grammar)
	
	return abstract_lr1_construction(
		pim, grammar,
		front=front, note_reduce=note_reduce,
		initial_follow=None,
		lr0_catalog=lr0.bft.catalog,
	)



class ConflictData(NamedTuple):
	tokens: dict[str, set[int]]  # The rules that conflict on this token
	rules: dict[int, set[str]]  # The tokens that conflict on this rule.


def find_conflicts(graph, reduce_sets, grammar) -> list[ConflictData]:
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
		degree = Counter(state.shift.keys())  # This picks up some nonterminals but they do no harm.
		for rule_id in state.reduce:
			for token in reduce_sets[q, rule_id]:
				prefer_shift = token in state.shift and grammar.decide_shift_reduce(token, rule_id) == RIGHT
				if not prefer_shift: degree[token] += 1
		conflicted_tokens = set(token for token, count in degree.items() if count > 1)
		conflict = ConflictData({token: set() for token in conflicted_tokens}, {})
		for rule_id in state.reduce:
			contribution = conflicted_tokens & reduce_sets[q, rule_id]
			conflict.rules[rule_id] = contribution
			for token in contribution: conflict.tokens[token].add(rule_id)
		result.append(conflict)
	return result

