"""
--- DISCLAIMER: --- This file is not expected to "work", or even necessarily parse. ---

Discarded ideas go here: they may be educational but they are not the current direction of the project.

This module is quite deliberately not maintained.

Then again, project direction has changed before.
"""
from .support import foundation
from boozetools.macroparse.compaction import most_common, is_homogeneous

def multi_append(table:dict, row:dict):
	"""
	Utility function for collections of parallel arrays; these often have better
	storage and encoding characteristics than arrays of records do.
	:param table: A dictionary in which several keys point to lists.
	:param row: A dictionary; the values get appended to the corresponding lists in `table`.
	:return: Nothing.
	"""
	for key, value in row.items(): table[key].append(value)


def modified_aho_corasick_encoding(*, initial: dict, matrix: list, final: dict, jam: int) -> dict:
	"""
	Alfred V. Aho and Margaret J. Corasick discovered a truly wonderful algorithm for a particular class
	of string search problem in which there are both many needles and lots of haystack data. It works by
	the construction of a TRIE for identifying needles, together with a failure pointer for what state to
	enter if the present haystack character is not among the outbound edges from the current state. The
	structure so constructed is queried at most twice per character of haystack data on average, because
	the failure pointers always point to a node at least one edge less deep into the TRIE.

	That structure provides the inspiration for a fast, compact encoding of an arbitrary DFA. The key
	idea is to find, for each state, the least-cost "default transition", defined according to how much
	storage gets used under the rules for that case. We begin with the most common transition within
	the row, but then scan over prior states looking for a good template: a "shallower" state with
	many transitions in common. It is then sufficient to store the identity of that default pointer
	and a sparse list of exceptions. If the sparse list results in expansion, a dense row may be stored
	instead. If the exceptions are all identical, they may be stored as a single integer rather than a list.

	Upon further reflection: sometime states at the same distance-from-root have the most in common.
	A probe takes constant amortized time as long as the fail-over path length is restricted to a constant
	multiple of the node's depth. That constant probably need not be more than one for excellent results.
	"""
	# Renumber the states according to a breadth-first topology, and also determine the resulting
	# depth boundaries. (A topological index would suffice, but this has other nice properties.)
	assert jam == -1
	bft = foundation.BreadthFirstTraversal()
	states = []
	
	def renumber(src): states.append([jam if dst == jam else bft.lookup(dst) for dst in matrix[src]])
	
	initial = {condition: (bft.lookup(q0), bft.lookup(q1)) for condition, (q0, q1) in initial.items()}
	bft.execute(renumber)
	depth = bft.depth_list()
	
	# Next, we need to construct the compressed structure. For simplicity, this will be three arrays
	# named for their function and indexed by state number.
	delta = {'default': [], 'index': [], 'data': [], }
	result = {'delta': delta, 'initial': initial, 'final': [bft.lookup(q) for q in final.keys()],
	          'rule': list(final.values())}
	failover_path_length = []
	metric = 0
	for i, row in enumerate(states):
		# Find the shortest encoding, possibly by reference to earlier states:
		default = most_common(row)
		index = [k for k, x in enumerate(row) if x != default]
		data = [row[k] for k in index]
		cost = len(index) + (1 if is_homogeneous(data) else len(data))
		for j in range(i):
			if failover_path_length[j] <= depth[i]:
				try_index = [k for k, x in enumerate(states[j]) if x != row[k]]
				try_data = [row[k] for k in try_index]
				try_cost = len(try_index) + (1 if is_homogeneous(try_data) else len(try_data))
				if try_cost < cost: default, index, data, cost = -2 - j, try_index, try_data, try_cost
		# Append the chosen encoding into the structure:
		if cost < len(row):  # If the compression actually saves space on this row:
			if is_homogeneous(data): data = data[0] if data else default
			multi_append(delta, {'default': default, 'index': index, 'data': data})
			failover_path_length.append(0 if default > -2 else 1 + failover_path_length[-2 - default])
		else:  # Otherwise, a dense storage format is indicated by eliding the list of indices.
			multi_append(delta, {'default': jam, 'index': None, 'data': row})
			cost = len(row)
			failover_path_length.append(0)
		metric += 1 + cost
	# At this point, the DFA is represented in about as terse a format as makes sense.
	raw_size = len(matrix) * len(matrix[0])
	print('Matrix compressed into %d cells (%0.2f%% of %d * %d = %d) with at most %d probes per character scanned.' % (
	metric, 100 * metric / raw_size, len(matrix), len(matrix[0]), raw_size, 1 + max(failover_path_length)))
	return result

def aho_corasick_style_scanner_delta_function(*, index, data, default) -> callable:
	""" This decodes the above compaction by following `default` pointers as needed until an answer is found. """
	probe = sparse_table_function(index=index, data=data)
	def fn(state_id:int, symbol_id:int) -> int:
		if state_id<0: return state_id
		q = probe(state_id, symbol_id)
		if q is None:
			d = default[state_id]
			return d if d > -2 else fn(-2-d, symbol_id)
		else: return q
	return fn

def old_parser_action_function(*, index, data, default) -> callable:
	""" This part adds the "default reductions" layer atop a naive representation of a sparse action table. """
	probe = sparse_table_function(index=index, data=data)
	def fn(state_id:int, symbol_id:int) -> int:
		q = probe(state_id, symbol_id)
		return default[state_id] if q is None else q
	return fn

def old_parser_goto_function(*, state_class, class_list ) -> callable:
	def probe(state_id:int, nonterminal_id:int):
		cls = state_class[state_id]
		return 0-cls if cls < 0 else class_list[cls][nonterminal_id]
	return probe


def sparse_table_function(*, index, data) -> callable:
	"""
	The very simplest Python-ish "sparse matrix", and plenty fast on modern hardware, for the
	size of tables this module will probably ever see, is an ordinary Python dictionary from
	<row,column> tuples to significant table entries. There are better ways if you program
	closer to the bare metal, but this serves the purpose.

	This routine unpacks "compressed-sparse-row"-style data into an equivalent Python dictionary,
	then returns a means to query said dictionary according to the expected 2-dimensional interface.
	"""
	hashmap = {}
	for row_id, (Cs, Ds) in enumerate(zip(index, data)):
		if isinstance(Ds, int):  # All non-blank cells this row have the same value:
			for column_id in Cs: hashmap[row_id, column_id] = Ds
		else:
			for column_id, d in zip(Cs, Ds) if Cs else enumerate(Ds):
				hashmap[row_id, column_id] = d
	return lambda R, C: hashmap.get((R, C))


def compress_action_table(matrix: list) -> dict:
	"""
	Produce a compact representation of the "ACTION" table for a typical shift-reduce parser.
	:param matrix: list-of-lists of parse actions: positive numbers are shifts; negative are reductions, zero is error.
	:return: a compact structure.

	For each state in the ACTION table, the reduction with the largest lookahead set becomes a
	default reduction, so that only exceptions need be stored. This can delay the detection of
	a syntax error until several reductions have taken place, but it does not change the set
	of strings accepted as part of the language. Also, unless measures are taken to track the
	deepest state before the last round of reductions, it can throw away information useful to
	compute a set of valid expected next tokens in an error condition.

	Two subtleties affect the above strategy:
	1. Non-associativity declarations can result in	cells which MUST error despite being in
	   states which otherwise may have a default reduction. These can be expressly included in
	   the list of exceptions to the default.
	2. Error productions result in states that shift on the ERROR token. These states should
	   not get default-reductions -- or if they do, then the above-styled special measures
	   MUST be taken to ensure that the most suitable error production is finally used.

	This parsing library doesn't yet support error productions, so I'm only going to worry
	about the first case for now. Error productions might be a nice enhancement.

	The encoding of actions here is the same as is used in automata.DragonBookTable.
	"""
	
	def find_default_reduction(row: list) -> int:
		rs = [x for x in row if x < 0]
		return most_common(rs) if rs else 0
	
	raw_size = len(matrix) * len(matrix[0])
	print('Action table begins with %d states and %d columns (%d cells).' % (len(matrix), len(matrix[0]), raw_size))
	metric = 0
	delta = {'default': [], 'index': [], 'data': []}
	for q, row in enumerate(matrix):
		reduction = find_default_reduction(row)
		becomes_default = (reduction, 0)
		idx = [i for i, x in enumerate(row) if x not in becomes_default and (q, x) not in essential_errors]
		if len(idx) * 2 < len(row):
			multi_append(delta, {'default': reduction, 'index': idx, 'data': [row[k] for k in idx]})
			metric += 3 + 2 * len(idx)
		else:
			multi_append(delta, {'default': 0, 'index': None, 'data': row})
			metric += 2 + len(row)
	print("Compact form takes %d cells (%0.2f%%)." % (metric, 100 * metric / raw_size))
	return delta

class UnitReductionEliminator:
	def __init__(self, grammar: "ContextFreeGrammar", bft: foundation.BreadthFirstTraversal):
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

class HFA:
	"""
	These bits used to live on the parsing.automata.HFA class, but then I saw the light:
	THe HFA is a model. Constructing text about the model is just one possible way to
	view the model. That is a view's responsibility. So these bits go away.
	"""
	def earley_core(self, q:int):
		""" Maybe we need to know the core-items that a state began from, stripped of look-ahead powers. """
		return sorted(set((r,p) for r, p, *_ in self.bft.traversal[q]))
	
	def display_situation(self, q: int, lookahead: str):
		"""
		Used for diagnostic displays:
			How might I get to state #q, in symbols?
			What would that parser situation look like?
		"""
		head, *tail = self.bft.shortest_path_to(q)
		print('==============\nIn language %r, consider:' % self.grammar.start[self.initial.index(head)])
		print('\t' + ' '.join(map(self.bft.breadcrumbs.__getitem__, tail)), pretty.DOT, lookahead)

class DeterministicStyle(ParsingStyle):
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

###########
#
#  The old broken version of the minimal-LR1 thing


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
		apply to nonterminal `symbol`.

		`follower` may be `None` to mean "the non-conflicted portion of the reduce set,
		or may be a specific reduce-set token.

		`goto_transparent` means there is an epsilon-only path through any
		remaining portion of the rule :param symbol: appeared in, so that reduce-set
		conflicts should be propagated to these resulting parse-items.

		`iso_q` is the ID number in the LR(0)/LALR graph corresponding to the
		LR(1) state under construction.

		The complexity here comes from how this algorithm threads the needle between
		LALR-when-adequate and LR(1)-when-necessary.
		"""
		items = []
		goto_q = lr0.graph[iso_q].shift[symbol]
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


