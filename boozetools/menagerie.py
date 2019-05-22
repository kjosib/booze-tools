"""
Discarded ideas go here: they may be educational but they are not the current direction of the project.

This module is quite deliberately not maintained.

Then again, project direction has changed before.
"""
from . import foundation
from .compaction import most_common, is_homogenous

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
		cost = len(index) + (1 if is_homogenous(data) else len(data))
		for j in range(i):
			if failover_path_length[j] <= depth[i]:
				try_index = [k for k, x in enumerate(states[j]) if x != row[k]]
				try_data = [row[k] for k in try_index]
				try_cost = len(try_index) + (1 if is_homogenous(try_data) else len(try_data))
				if try_cost < cost: default, index, data, cost = -2 - j, try_index, try_data, try_cost
		# Append the chosen encoding into the structure:
		if cost < len(row):  # If the compression actually saves space on this row:
			if is_homogenous(data): data = data[0] if data else default
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


def compress_action_table(matrix: list, essential_errors: set) -> dict:
	"""
	Produce a compact representation of the "ACTION" table for a typical shift-reduce parser.
	:param matrix: list-of-lists of parse actions: positive numbers are shifts; negative are reductions, zero is error.
	:param essential_errors: set of pairs of (state_id, terminal_id) which MUST NOT go to a default reduction.
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

	The encoding of actions here is the same as is used in context_free.DragonBookTable.
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

