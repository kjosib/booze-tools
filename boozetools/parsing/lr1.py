from collections import defaultdict

from ..support.foundation import transitive_closure, BreadthFirstTraversal
from .interface import END_OF_TOKENS
from .context_free import ContextFreeGrammar, Rule
from .automata import HFA, LookAheadState, reachable, LR0_State
from .lr0 import lr0_construction, ParseItemMap, ParseItem

def canonical_lr1(grammar: ContextFreeGrammar) -> HFA[LookAheadState]:
	"""
	Before embarking on a quest to produce a minimal-LR(1) table by sophisticated
	methods, it's worth learning how to produce the maximal-LR(1) table by (some
	variant of) Donald E. Knuth's original method.

	A Knuth parse-item is like an LR(0) item augmented with the (1) next token
	expected AFTER the corresponding rule would be recognized. The initial core
	would look like { .S/# } in the usual notation. Otherwise, the algorithm has
	much in common with the LR(0) construction.
	"""
	
	def build_state(core: frozenset):
		
		def visit(lr1_item):
			item_index, follower = lr1_item
			pi = parse_items[item_index]
			if pi.next_symbol is None:
				if pi.rule_id is not None:
					reduce[follower].append(pi.rule_id)
			else:
				shifted_index = item_index + 1
				shifted_cores[pi.next_symbol].add((shifted_index, follower))
				for head_item in symbol_front.get(pi.next_symbol, ()):
					for after in parse_items[shifted_index].read_set:
						yield head_item, after
					if is_transparent(shifted_index):
						yield head_item, follower
		
		shifted_cores, reduce = defaultdict(set), defaultdict(list)
		transitive_closure(core, visit)
		shift = {
			symbol:bft.lookup(frozenset(item_set), breadcrumb=symbol)
			for symbol, item_set in reachable(shifted_cores, reduce, grammar).items()
		}
		graph.append(LookAheadState(shift=shift, reduce=reduce))
	
	pim = ParseItemMap.from_grammar(grammar)
	parse_items, symbol_front, language_front, transparent = pim
	is_transparent = transparent.__contains__
	bft = BreadthFirstTraversal()
	graph = []
	initial_items = [(i, END_OF_TOKENS) for i in language_front]
	initial = [bft.lookup(frozenset([item])) for item in initial_items]
	bft.execute(build_state)
	accept = [graph[qi].shift[language] for qi, language in zip(initial, grammar.start)]
	return HFA(graph=graph, initial=initial, accept=accept, bft=bft)

def _isocore(core):
	return frozenset(i for (i, f) in core)

def _read_set_function(parse_items, graph, nullable, terminals):
	"""
	A challenge can occur when a rule has several nullable symbols in a row.
	To get the read-set of a parse-item, you must consider carefully what is nullable.
	"""
	extended_terminals = {END_OF_TOKENS}.union(terminals)
	def read_set(item_index, follow_set, q):
		pi = parse_items[item_index]
		if pi.next_symbol is None: return follow_set
		state = graph[q]
		result_set = set(state.shift.keys())
		if pi.next_symbol in nullable:
			result_set.update(read_set(item_index+1, follow_set, state.shift[pi.next_symbol]))
		return result_set
	def inner(item_index, follow_set, q):
		return frozenset(read_set(item_index, follow_set or (), q)) & extended_terminals
	return inner

_EVERYTHING = None  # `None` stands for "everything" -- i.e. eager reduce.

def minimal_lr1(grammar: ContextFreeGrammar) -> HFA[LookAheadState]:
	"""
	The present stab at a "minimal" LR(1) algorithm is explained in the manual
	at https://boozetools.readthedocs.io/en/latest/minimal.html
	"""
	def clean(item_set):
		""" Drop needless follow-sets; combine others. """
		iso_core = _isocore(item_set)
		iso_q = lr0.bft.catalog[iso_core]
		iso_state = lr0.graph[iso_q]
		if iso_state.is_adequate_reduce():
			# This test could probably be more generous but I'll have to think more.
			return frozenset((i, _EVERYTHING) for i in iso_core)
		else:
			follow = {i:set() for i,_ in item_set}
			for i, f in item_set:
				if f is not None:
					follow[i].update(f)
			return frozenset((i, frozenset(f) if f else None) for i,f in follow.items())
	
	def build_state(core:frozenset):
		def visit(lr1_item):
			item_index, follow_set = lr1_item
			pi = parse_items[item_index]
			if pi.next_symbol is None:
				if pi.rule_id is not None:
					if follow_set is None:
						note_reduce(pi.rule_id, None)
					else:
						for look_ahead in follow_set:
							note_reduce(pi.rule_id, look_ahead)
			else:
				shifted_index = item_index + 1
				shifted_cores[pi.next_symbol].add((shifted_index, follow_set))
				if pi.next_symbol in symbol_front:
					# i.e. next_symbol is a non-terminal:
					after_set = set(parse_items[shifted_index].read_set)
					if is_transparent(shifted_index) and follow_set is not None:
						after_set.update(follow_set)
					return front(iso_q, pi.next_symbol, frozenset(after_set))
		
		def note_reduce(rule_id, look_ahead):
			cell = reduce[look_ahead]
			if rule_id not in cell:
				cell.append(rule_id)
		
		iso_q = lr0.bft.catalog[_isocore(core)]
		shifted_cores, reduce = defaultdict(set), defaultdict(list)
		transitive_closure(core, visit)
		shift = {
			symbol:bft.lookup(clean(item_set), breadcrumb=symbol)
			for symbol, item_set in reachable(shifted_cores, reduce, grammar).items()
		}
		graph.append(LookAheadState(shift=shift, reduce=reduce))
	
	def front(iso_q, symbol, after_set):
		""" Starting parse-items for each rule for the prediction-symbol. """
		for head_item_index in symbol_front[symbol]:
			if (iso_q, head_item_index) in tainted:
				yield head_item_index, after_set
			else:
				yield head_item_index, _EVERYTHING
	
	# Step One: Basic Set Up
	pim = ParseItemMap.from_grammar(grammar)
	lr0 = lr0_construction(pim)  # This implicitly solves a lot of sub-problems.
	parse_items, symbol_front, language_front, transparent = pim
	is_transparent = transparent.__contains__

	# Step Two: The Tainting
	tainted = _tainted_items(parse_items, is_transparent, lr0.graph, grammar.rules)
	
	# Step Three: Build the Final Product
	bft = BreadthFirstTraversal()
	graph = []
	initial = [bft.lookup(c) for c in _initial_cores(lr0.initial, language_front, tainted)]
	bft.execute(build_state)
	accept = [graph[qi].shift[language] for qi, language in zip(initial, grammar.start)]
	return HFA(graph=graph, initial=initial, accept=accept, bft=bft)

def _initial_cores(initial_iso, language_front, tainted):
	follow_set = frozenset([END_OF_TOKENS])
	for qi, ii in zip(initial_iso, language_front):
		item = (ii, follow_set if (qi, ii) in tainted else _EVERYTHING)
		yield frozenset([item])

def _tainted_items(parse_items:list[ParseItem], is_transparent, graph:list[LR0_State], rules:list[Rule]) -> set:
	# This is kind of a transitive closure but half a step out of phase.
	# It might be possible to re-arrange it to be in phase, and thus call
	# some standard transitive-closure logic, but for now, this is it.
	
	# Commentary: If we tainted not only head-items
	# but actually every predecessor item along the way,
	# then it might be easier to decide when to drop more
	# follower-sets in the later phase "build_states".
	
	predecessors = _build_predecessors(graph)
	work_list = _initial_taints(parse_items, graph)
	tainted = set()
	while work_list:
		q, item_index = work_list.pop()
		pi = parse_items[item_index]
		head_item_index = item_index - pi.offset
		if pi.rule_id is None:
			# This means the taint applies to a language start-item,
			# so no further contagion is possible.
			for q_head in _n_steps(predecessors, {q}, pi.offset):
				taint = (q_head, head_item_index)
				tainted.add(taint)
		else:
			# The work-item points into a regular rule
			# with a regular follow-set.
			lhs = rules[pi.rule_id].lhs
			for q_head in _n_steps(predecessors, {q}, pi.offset):
				taint = (q_head, head_item_index)
				if taint not in tainted:
					tainted.add(taint)
					for ci in graph[q_head].closure:
						if parse_items[ci].next_symbol == lhs:
							if is_transparent(ci+1):
								work_list.append((q_head, ci))
	return tainted

def _build_predecessors(graph):
	predecessors = [[] for _ in range(len(graph))]
	for q, state in enumerate(graph):
		for p in state.shift.values():
			predecessors[p].append(q)
	return predecessors

def _initial_taints(parse_items:list[ParseItem], graph:list[LR0_State]):
	work_list = []
	for q, state in enumerate(graph):
		if state.has_conflict():
			for item_index in state.closure:
				if parse_items[item_index].next_symbol is None:
					work_list.append((q, item_index))
	return work_list

def _n_steps(arcs:list[list[int]], starts:set[int], n:int) -> set[int]:
	for _ in range(n):
		step = set()
		for q in starts:
			step.update(arcs[q])
		starts = step
	return starts
