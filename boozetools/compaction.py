"""
Parsing literature is rife with different approaches to encode scanner and parser tables
compactly, with all manner of trade-offs between size and access time.

It may be said that today's fast machines and big memories leave little need to compress these
tables. However, compression can help complex tables fit in cache. Alternatively, compact
forms may be used for storage and interchange while implementations reprocess the tables
for quicker operation despite a bigger RAM footprint: this still saves disk space.

Typically, tables used in different contexts have distinct structural characteristics which
make it more or less effective to compress them in particular ways. This module implements a
few typical approaches to compressing scanner and parser tables. The corresponding ways to
use them are implemented in the runtime.py module.

As a nod to runtime efficiency, offsets useful for a displacement table are precomputed here
and provided for later.
"""

import collections
from . import foundation

def multi_append(table:dict, row:dict):
	"""
	Utility function for collections of parallel arrays; these often have better
	storage and encoding characteristics than arrays of records do.
	:param table: A dictionary in which several keys point to lists.
	:param row: A dictionary; the values get appended to the corresponding lists in `table`.
	:return: Nothing.
	"""
	for key, value in row.items(): table[key].append(value)

def most_common_member(row):
	""" Return the most-common element in the array; break ties arbitrarily. """
	return collections.Counter(row).most_common(1)[0][0]

def is_homogenous(row):
	return len(row) < 2 or all(r == row[0] for r in row)
	

def modified_aho_corasick_encoding(*, initial:dict, matrix:list, final:dict, jam:int) -> dict:
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
	delta = {'default': [], 'index': [], 'data': [],}
	result = {'delta':delta, 'initial': initial, 'final': [bft.lookup(q) for q in final.keys()], 'rule': list(final.values())}
	failover_path_length = []
	metric = 0
	for i, row in enumerate(states):
		# Find the shortest encoding, possibly by reference to earlier states:
		default = most_common_member(row)
		index = [k for k,x in enumerate(row) if x != default]
		data = [row[k] for k in index]
		cost = len(index) + (1 if is_homogenous(data) else len(data))
		for j in range(i):
			if failover_path_length[j]<=depth[i]:
				try_index = [k for k,x in enumerate(states[j]) if x != row[k]]
				try_data = [row[k] for k in try_index]
				try_cost = len(try_index) + (1 if is_homogenous(try_data) else len(try_data))
				if try_cost < cost: default, index, data, cost = -2-j, try_index, try_data, try_cost
		# Append the chosen encoding into the structure:
		if cost < len(row): # If the compression actually saves space on this row:
			if is_homogenous(data): data = data[0] if data else default
			multi_append(delta, {'default': default, 'index':index, 'data': data})
			failover_path_length.append(0 if default > -2 else 1+failover_path_length[-2-default])
		else: # Otherwise, a dense storage format is indicated by eliding the list of indices.
			multi_append(delta, {'default': jam, 'index':None, 'data': row})
			cost = len(row)
			failover_path_length.append(0)
		metric += 1+cost
	# At this point, the DFA is represented in about as terse a format as makes sense.
	raw_size = len(matrix)*len(matrix[0])
	print('Matrix compressed into %d cells (%0.2f%%) with at most %d probes per character scanned.' % (metric, 100*metric/raw_size, 1+max(failover_path_length)))
	return result

def compress_action_table(matrix:list, essential_errors:set) -> dict:
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
	def find_default_reduction(row:list) -> int:
		rs = [x for x in row if x < 0]
		return most_common_member(rs) if rs else 0
	raw_size = len(matrix)*len(matrix[0])
	print('Action table begins with %d states and %d columns (%d cells).'%(len(matrix), len(matrix[0]), raw_size))
	metric = 0
	delta = {'default':[], 'index':[], 'data':[]}
	for q, row in enumerate(matrix):
		reduction = find_default_reduction(row)
		becomes_default = (reduction, 0)
		idx = [i for i,x in enumerate(row) if x not in becomes_default and (q,x) not in essential_errors]
		if len(idx) * 2 < len(row):
			multi_append(delta, {'default':reduction, 'index':idx, 'data':[row[k] for k in idx]})
			metric += 3 + 2 * len(idx)
		else:
			multi_append(delta, {'default': 0, 'index':None, 'data': row})
			metric += 2 + len(row)
	print("Compact form takes %d cells (%0.2f%%)."%(metric, 100*metric/raw_size))
	return delta

def compress_goto_table(goto_table:list) -> dict:
	"""
	Produce a compact representation of the "GOTO" table for a typical shift-reduce parser.
	:param goto_table: [state][nonterminal] contains the state ID for that nonterminal appearing in that state.
	:return: a compact structure.
	
	In a GOTO table, zeros are "don't-care" entries, because they represent situations that
	are unreachable if the table construction algorithm is correct. There tends to be a lot of
	repetition for any given nonterminal, and most states have only a small handful of entries.
	
	This algorithm uses a per-state equivalence-class idea exploiting the prevalence of
	irrelevant/unreachable cells in the dense-matrix representation. Finding the very best
	possible set of such classes seems like it's probably NP-hard, so this algorithm uses
	the simplistic plan of a linear scan. On balance, it should still produce decent results.
	
	Upon further reflection, it appears that many states have only a single possible "goto";
	in this cases the indirection through the equivalence class list need not apply, and thus
	even fewer equivalence classes should be created.
	"""
	def find_class(row) -> int:
		distinct = set(row)
		distinct.discard(0)
		if len(distinct) == 1: return 0-distinct.pop()
		for class_id, row_class in enumerate(class_list):
			if compatible(row, row_class):
				merge(row, row_class)
				return class_id
		return foundation.allocate(class_list, list(row))
	
	def compatible(row, row_class): return all(r==0 or c==0 or r==c for r,c in zip(row, row_class))
	
	def merge(row, row_class):
		for i,r in enumerate(row):
			if r != 0:
				if row_class[i] == 0: row_class[i] = r
				else: assert row_class[i] == r
	
	print("GOTO table original size:", sum(map(len, goto_table)))
	class_list = []
	state_class = [find_class(row) for row in goto_table]
	print("GOTO compact size:", sum(map(len, class_list))+len(state_class))
	return {'state_class': state_class, 'class_list': class_list}


