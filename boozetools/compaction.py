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

def modified_aho_corasick_encoding(*, initial:dict, matrix:list, final:dict, jam:int) -> dict:
	"""
	Alfred V. Aho and Margaret J. Corasick discovered a truly wonderful algorithm for a particular class
	of string search problem in which there are both many needles and lots of haystack data. It works by
	the construction of a TRIE for identifying needles, together with a failure pointer for what state to
	enter if the present haystack character is not among the outbound edges from the current state. The
	structure so constructed is queried at most twice per character of haystack data on average, because
	the failure pointers always point to a node at least one edge less deep into the TRIE.
	
	That structure provides the inspiration for a fast, compact encoding of an arbitrary DFA. The key
	idea is to find, for each state, the shallower state with the most transitions in common.
	It is then sufficient to store the identity of that "fail-over" state and a sparse list
	of exceptions. If the sparse list results in expansion, a dense row may be stored instead.
	
	For the sake of brevity, the "jam state" is implied to consist of nothing but jam-transitions, and
	is not explicitly stored.
	"""
	# Renumber the states according to a breadth-first topology, and also determine the resulting
	# depth boundaries. (A topological index would suffice, but this has other nice properties.)
	assert jam < 0
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
	for i, row in enumerate(states):
		# Find the shortest encoding by reference to shallower states:
		pointer, best = jam, [k for k,x in enumerate(row) if x != jam]
		for j in range(i):
			if depth[j] == depth[i]: break # This relies on the depth-first ordering...
			contender = [k for k,x in enumerate(states[j]) if x != row[k]]
			if len(contender) < len(best): pointer, best = j, contender
		# Append the chosen encoding into the structure:
		if len(best) * 2 < len(row): # If the compression actually saves space on this row:
			multi_append(delta, {'default': pointer, 'index':best, 'data': [row[k] for k in best]})
		else: # Otherwise, a dense storage format is indicated by eliding the list of indices.
			multi_append(delta, {'default': jam, 'index':None, 'data': row})
	# At this point, the DFA is represented in about as terse a format as makes sense.
	metric = 2*len(delta['default']) + sum(map(len, delta['data'])) + sum(x is None or len(x)+1 for x in delta['index'])
	delta['offset'] = first_fit_decreasing(delta['index'])
	print('Matrix compressed into %d cells.' % metric)
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
		histogram = collections.Counter()
		for x in row:
			if x < 0: histogram[x] += 1
		return max(histogram.keys(), key=histogram.get, default=0)
	
	delta = {'default':[], 'index':[], 'data':[]}
	for q, row in enumerate(matrix):
		reduction = find_default_reduction(row)
		becomes_default = (reduction, 0)
		idx = [i for i,x in enumerate(row) if x not in becomes_default and (q,x) not in essential_errors]
		if len(idx) * 2 < len(row):
			multi_append(delta, {'default':reduction, 'index':idx, 'data':[row[k] for k in idx]})
		else:
			multi_append(delta, {'default': 0, 'index':None, 'data': row})
	delta['offset'] = first_fit_decreasing(delta['index'])
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


def first_fit_decreasing(indices:list) -> list:
	"""
	(Aho and Ulman [2]) and (Ziegler [7]) advocate this scheme...
	This function finds a set of displacements such that no two index[i][j]+displacement[i] are the same.
	The entry in list `indices` is normally a list of columns within a given row which are considered to
	have legitimate data in some particular sparse matrix.
	
	The result can be used to populate a displacement table from "compressed sparse rows",
	eliminating a search each time the table gets probed.
	
	I've chosen to expand on the idea slightly: If a row is denser than 50%, it makes more sense to store
	the row as a dense vector. Such rows get `None`/null in their column index and corresponding offset.
	"""
	used = set()
	def first_fit(row:list) -> int:
		offset = 0
		while any(r+offset in used for r in row): offset += 1
		used.update(r+offset for r in row)
		return offset
	displacements = [None] * len(indices)
	for i in sorted([i for i, row in enumerate(indices) if row], key=lambda i: len(indices[i])):
		displacements[i] = first_fit(indices[i])
	return displacements

