"""
Discarded ideas go here: they may be educational but they are not the current direction of the project.

This module is quite deliberately not maintained.

Then again, project direction has changed before.
"""
from . import foundation
from .compaction import most_common_member, is_homogenous, multi_append
from .runtime import sparse_table_function

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
		default = most_common_member(row)
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
