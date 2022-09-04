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

