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

import collections, bisect
from typing import List, Optional, Tuple, Sequence, Set
from . import foundation, expansion

VERBOSE = False

###
###  A few convenient abbreviations: Skip them on first reading.
###

def most_common(row, *, default=0):
	""" Return the most-common element in the array; break ties arbitrarily. """
	C = collections.Counter(row)
	return C.most_common(1)[0][0] if C else default

def is_homogeneous(row): return len(row) < 2 or all(r == row[0] for r in row)

def heavy_rows(matrix):
	""" Return the indices of rows that are more-than-half full. Fullness == Truthiness. """
	return [r for r, row in enumerate(matrix) if sum(map(bool, row)) * 2 > len(row)]

def lighten(row):
	""" Preserve `None` (as don't-care); logical-NOT the rest. """
	return tuple(None if x is None else int(not x) for x in row)

def measure_approximate_cost(structure):
	""" Various bits estimate the size of the structures they return. This makes that consistent. """
	if isinstance(structure, (list, tuple)): return 1 + sum(map(measure_approximate_cost, structure))
	elif isinstance(structure, dict): return len(structure) + sum(map(measure_approximate_cost, structure.values()))
	elif isinstance(structure, int) or structure is None: return 1
	else: assert False, type(structure)

###
###  Leitmotifs: Recognizable themes that get used over and over...
###

def find_row_equivalence(matrix, do_not_care) -> Tuple[List[int], List[List]]:
	"""
	:param matrix: A rank-two tensor. Iterable of rows.
	:param do_not_care: Cells with this value may be assigned any convenient value for the purpose.
	"""
	index, classes = [], []
	for row in matrix:
		for class_id, candidate_class in enumerate(classes):
			if all(a == b or do_not_care in (a, b) for a, b in zip(row, candidate_class)):
				index.append(class_id)
				for c, value in enumerate(row):
					if value != do_not_care: candidate_class[c] = value
				break
		else:
			index.append(foundation.allocate(classes, list(row)))
	return index, classes

def find_column_equivalence(matrix, do_not_care) -> Tuple[List[int], List[Sequence]]:
	""" Adapt find_row_equivalence (above) to work on columns instead of rows. """
	index, classes = find_row_equivalence(zip(*matrix), do_not_care)
	return index, list(zip(*classes))

def first_fit_decreasing(indices:list, *, allow_negative:bool) -> Tuple[List[int], int] :
	"""
	(Aho and Ulman [2]) and (Ziegler [7]) advocate this scheme...
	This function finds a set of displacements such that no two index[i][j]+displacement[i] are the same.
	
	This is part of a strategy for compact representation of a sparse matrix
	with fast O(1) read performance. The input to THIS function is a statement
	about which cells in the original matrix contain non-trivial data:
	`col in indices[row]` exactly when `matrix[row][column]` is non-trivial.

	The result can be used to populate a displacement table, which is a simple kind of perfect-hash.
		* A hash is "perfect" when it requires at most one probe to determine
		the presence or absence of a key; in general these must be precomputed.
		* A hash is "minimal" when (in the lingo of hashing) all the buckets are used.
		* The holy grail of "minimal perfect hashing" generally requires a more complex function.
	
	Rows are considered in decreasing order of density, so if Zipf's law applies then the result
	will tend to be packed fairly densely: i.e. minimal or nearly so. This tends to be true of the
	way this particular function gets used in this library.
	
	The size of the necessary resulting vector is also returned: it would have to be determined again
	in every reasonable case otherwise.
	
	A final note: empty input rows are assigned the offset equal to the size of the implied check-vector.
	"""
	used = set()
	def first_fit(row: List[int]) -> int:
		offset = 0 - min(row) if allow_negative else 0
		while any(r + offset in used for r in row): offset += 1
		used.update(r + offset for r in row)
		return offset
	
	displacements = [0] * len(indices) # Allocate space; it will be filled out-of-order.
	populations = list(map(len, indices))
	schedule = iter(foundation.grade(populations, descending=True))
	for i in schedule:
		if indices[i]: displacements[i] = first_fit(indices[i])
		else: break # All remaining should be set == size of implied check vector.
	size = max(used)+1 if used else 0
	for i in schedule: displacements[i] = size
	if VERBOSE: print("First-Fit Decreasing placed %d entries among %d positions."%(len(used), size))
	return displacements, size

def encode_boolean_field_as_offset_check(matrix:Sequence[Sequence[Optional[bool]]]):
	"""
	This is used in both the scanner and parser tables for keeping track of the error plane.
	This function does not worry about equivalence classification.
	It returns a pair of vectors such that:
		check[offset[row]+column] == column
	is equivalent to:
		bool(matrix[row][column])
	The returned structure is smaller when it has fewer `True` entries to encode.
	"""
	ones = [set(c for c,flag in enumerate(row) if flag) for row in matrix]
	offset, size = first_fit_decreasing(ones, allow_negative=True)
	check = [-1] * size
	for r, (base, cs) in enumerate(zip(offset, ones)):
		for c in cs: check[base+c] = r
	return offset, check

def encode_displacement_function(exceptions:list):
	"""
	This builds a typical textbook-style displacement table: a simple kind of perfect-hash,
	which may not be minimal but it's usually decently close.
	:param exceptions: a list of dictionaries; keys are column numbers, values are destination state numbers.
	No attempt is made to coalesce similar or identical rows here:
		(1) It's the caller's responsibility.
		(2) Only the caller knows the best way to perform such a feat.
	There's no guarantee two distinct rows might not get the same offset, so the only
	reliable check-value is the row number. BISON uses the column number instead,
	but it also enforces distinct offsets for all rows.
	"""
	offset, size = first_fit_decreasing(exceptions, allow_negative=True)
	check = [-1]*size
	value = [0]*size
	for row_id, row_dict in enumerate(exceptions):
		row_offset = offset[row_id]
		for column, entry in row_dict.items():
			index = row_offset + column
			assert check[index] == -1
			check[index] = row_id
			value[index] = entry
	return {'offset': offset, 'check': check, 'value':value}

###
###  Major supporting themes: this is where the alleged "deep magic" lives.
###

def compress_dfa_delta_function(matrix:list) -> dict:
	"""
	Per issue #8: A possibly-novel approach to condensing large scanner tables.
	The method is described at https://github.com/kjosib/booze-tools/issues/8
	"""
	# Splitting the matrix into two planes (residue and exceptions):
	zeros, ones, residue, exceptions = [], [], [], []
	for row in matrix:
		common = [k for k,v in collections.Counter(row).most_common(2) if v > 1]
		zeros.append(common[0])
		ones.append(common[-1]) # Because if len(common) == 1, duplicate it.
		look_up = {v:i for i,v in enumerate(common)}
		residue.append([look_up.get(v) for v in row])
		exceptions.append({c:x for c,x in enumerate(row) if x not in common})
	# Compacting the residue plane (a partially-null boolean matrix) by means of equivalence classification:
	column_class, residue = find_column_equivalence(residue, None)
	for i in heavy_rows(residue):
		zeros[i], ones[i] = ones[i], zeros[i]
		residue[i] = lighten(residue[i])
	row_class, residue = find_row_equivalence(residue, None)
	# Converting the final residue to a set-as-displacement-table representation:
	offset, check = encode_boolean_field_as_offset_check(residue)
	# Tie a pretty bow around it:
	return {
		'exceptions': encode_displacement_function(exceptions),
		'bg': {
			# For most states, the most common entry is the error transition. Thus: exceptions to that rule:
			'zero': list(zip(*[(index, value) for index, value in enumerate(zeros) if value != -1])),
			'one': ones,
			'row_class': row_class, 'col_class': column_class,
			'offset': offset, 'check': check,
		},
	}

def compress_scanner(*, initial:dict, matrix:list, final:dict) -> dict:
	height, width = len(matrix), len(matrix[0])
	delta = compress_dfa_delta_function(matrix)
	metric = measure_approximate_cost(delta)
	if VERBOSE: print("DFA matrix was %d rows, %d cols = %d cells; compact form is about %d cells (%0.2f%%)"%(
		height, width, height * width, metric, (100.0*metric/(height*width))
	))
	return {'delta': delta, 'initial': initial, 'final': list(final.keys()), 'rule': list(final.values()),}

def decompose_by_default_reduction(matrix:list, essential_errors:set, recovering_states):
	"""
	The first phase of compacting a parser's "ACTION" table.
	The idea is to separate the matrix into a "default" entry per row
	and a set of exceptions, which can presumably be stored in a lot
	less space.
	
	:param matrix: The initial ACTION matrix is a row for each state;
		the columns correspond to the terminals, and every cell has
		a specific instruction.
	:param essential_errors: (state, terminal_id) pairs which, due to
		non-assoc declarations, must absolutely reflect a syntax error.
		As such, if those states have a default-reduction, then corresponding
		error entries must explicitly appear in the "residue" matrix
	:param recovering_states: These states are REACHED BY the error token.
		To avoid an excess of false restarts, these states may not use
		a default-reduction.
	:return: default-reduction vector and residue matrix where allowed entries have been turned to `None`.
	"""
	reduce = [most_common([a for a in row if a < 0]) for row in matrix] # Default Reduction Table
	for q in recovering_states: reduce[q] = 0
	residue = [[
		value if (q,column) in essential_errors or value not in (0, default) else None
		for column, value in enumerate(row)
	] for q, (row, default) in enumerate(zip(matrix, reduce))]
	return reduce, residue

def decompose_by_edit_distance(action:List[List[int]], focus:List[Set[int]]):
	"""
	This is one area where performance did become a real problem with a simple approach.
	Therefore, I've thought about things and come up with something I can be reasonably
	proud of. All hail the well-considered loop invariant!
	
	The basic idea is:
		1. The outer loop works subject rows in order of _IN_creasing "population".
		2. The inner loop compares against (already-solved) rows in _DE_creasing population.
		3. (Critical) An arithmetic test shows when the inner loop becomes hopeless.
	
	There are a thousand subtle ways to get this wrong. I've tried most of them.
	The trick to getting it right is stating the correct post-condition in terms
	that are easy to verify. Here's the latest try:
	
	The edit-chain from R covers at least the columns in `focus[R]` and matches `action[R]`.
	A useful intermediate datum is which cells are covered by some fallback chain.
	"""
	
	def find_edits(subject, basis, must_cover, basis_covers):
		# If the basis covers it WRONGLY, it must be an edit.
		# If it must be covered and the basis does not, it's an edit.
		# But if the basis covers it correctly, then it's not an edit.
		return [
			c for c in must_cover|basis_covers
			if not (c in basis_covers and basis[c] == subject[c])
		]
	
	def find_best_fallback():
		subject, must_cover = action[current], focus[current]
		fb, best = -1, {c:subject[c] for c in must_cover}
		for size, candidate in reversed(solved):
			if len(best) + size < len(must_cover): break
			golf = find_edits(subject, action[candidate], must_cover, focus[candidate])
			if len(golf) < len(best): fb,best = candidate,golf
		must_cover.update(focus[fb])
		return fb, {c:subject[c] for c in best}
	
	assert len(action) == len(focus)
	fallback = [-1] * len(action)
	edits = [None] * len(action)
	solved = []
	for current in foundation.grade(list(map(len, focus))):
		fallback[current], edits[current] = find_best_fallback()
		if edits[current]: bisect.insort_right(solved, (len(focus[current]), current))
	return fallback, edits

def compress_action_table(action:List[List[int]], nonassoc_errors:set) -> dict:
	"""
	Produce a compact representation of the "ACTION" table for a typical shift-reduce parser.
	:param action: matrix of parse actions: positive numbers are shifts; negative are reductions, zero is error.
	:param nonassoc_errors:
	    set of pairs of (from_state_id, terminal_id) which must error on account of
	    non-associativity declarations. They are important for two reasons:
	    1. Mentioned states must not become "interactive".
	    2. These error-cells are likely to be isolated, and so good candidates
	       for the reduction-plane to treat as "don't-care": they'll be picked
	       up in the shift-plane anyway.
	:return: a compact structure.
	"""
	height, width = len(action), len(action[0]) # Stats for comparison to the compression method
	
	reduce = compose_reduce_plane(action, nonassoc_errors)
	model = expansion.parser_reduce_function(**reduce)
	focus = [ # A boolean map of where the model gets it wrong.
		set(c for c,i in enumerate(row) if model(r,c) != i)
		for r,row in enumerate(action)
	]
	fallback, edits = decompose_by_edit_distance(action, focus)
	for q,t in nonassoc_errors:
		if fallback[q] == -1 and not edits[q]:
			fallback[q] = -2 # By the way, is this even possible?
	edit_table = encode_displacement_function(edits)
	result = {'reduce': reduce, 'fallback': fallback, 'edits': edit_table,}
	metric = measure_approximate_cost(result)
	if VERBOSE: print("Action matrix was %d * %d = %d; compressed to %d (%0.2f%%)"%(
		height, width, height*width, metric, (100.0*metric)/(height*width)
	))
	return result

def compress_goto_table(goto_table:list) -> dict:
	"""
	Per issue #4: Look alternately for rows or columns with but a single remaining
	significant value. Record this value in a "quotient" list, together with bookkeeping
	data for the rows and columns. Afterwards, we are left with a much smaller residue matrix;
	typical equivalence-class methods may be used upon it.
	
	I didn't make this up. Unfortunately I cannot recall where I saw it in the literature, for
	it was a very long time ago. If anyone knows who invented this, or what article originally
	introduced it, I would very much like to hear from you.
	"""
	
	def remaining(index): return [r for r, x in enumerate(index) if x is None]
	def significant_cells(index, vector): return [v for x,v in zip(index, vector) if x is None and bool(v)]
	def homogenize(vector):
		if len(vector) < 1: return -1
		if is_homogeneous(vector): return vector[0]
	def compact(target_index, second_index, read):
		# This takes some pains to keep the quotient list small. It could be very slightly better...
		tmp = [(homogenize(significant_cells(second_index, read(r))), r) for r in remaining(target_index)]
		for q, i in sorted((q, i) for (q,i) in tmp if q is not None):
			if quotient[-1] != q: quotient.append(q)
			target_index[i] = len(quotient) - 1
	
	# Find rows/columns to zap, accumulating the "quotient" list:
	height, width = len(goto_table), len(goto_table[0])
	row_index, col_index, quotient = [None]*height, [None]*width, [-1]
	while True:
		hi_water_mark = len(quotient)
		compact(row_index, col_index, goto_table.__getitem__)
		compact(col_index, row_index, lambda c:[row[c] for row in goto_table])
		if len(quotient) == hi_water_mark: break
	
	# Capture the much smaller residue matrix:
	row_residue = remaining(row_index)
	column_residue = remaining(col_index)
	residue_matrix = [[row[e] for e in column_residue] for row in [goto_table[e] for e in row_residue]]
	
	# Minimize the residue.
	row_class, minimal_rows = find_row_equivalence(residue_matrix, 0)
	col_class, minimal_columns = find_row_equivalence(zip(*minimal_rows), 0)
	
	# Try to figure the ideal column-class ordering to make it fit better:
	col_class_offset = foundation.collation([vector.count(0) for vector in minimal_columns])
	minimal_rows = [{col_class_offset[c]:x for c, x in enumerate(row) if x} for row in zip(*minimal_columns)]
	
	# Build a single "residue vector" and row-offsets for efficient packing of the residue.
	row_class_offset, size = first_fit_decreasing(minimal_rows, allow_negative=False)
	residue = [0]*size
	for r_off, row in zip(row_class_offset, minimal_rows):
		for c_off, value in row.items():
			if value: residue[r_off+c_off] = value
	
	# Fill the holes in the foo_index vectors using the offsets corresponding to the equivalence classes:
	for state_id, cls_id in zip(row_residue, row_class):
		row_index[state_id] = row_class_offset[cls_id] + hi_water_mark
	for nonterm_id, cls_id,  in zip(column_residue, col_class):
		col_index[nonterm_id] = col_class_offset[cls_id] + hi_water_mark
	
	# Wrap up and return.
	if VERBOSE: print("GOTO table original size: %d rows, %d columns -> %d cells"%(height, width, height * width))
	result = {'row_index': row_index, 'col_index': col_index, 'quotient': quotient+residue, 'mark': hi_water_mark}
	metric = measure_approximate_cost(result)
	if VERBOSE: print("GOTO compact size: %d (%.2f%%)"%(metric, 100.0*metric/(height * width)))
	return result

def compose_reduce_plane(action, nonassoc_errors):
	"""
	What's going on here?
	I want to try to retain the error entries, even in states with a default reduction.
	The glimmer of hope centers on a semantic partitioning of the ACTION table.
	"""
	
	def decide(i, dr):
		if i == 0: return False
		if i == dr: return True
		return None
	
	def best_d_reduce(row):
		x = [a for a in row if a < 0]
		if x:
			i, count = collections.Counter(x).most_common(1)[0]
			if count > 1: return i
		return 0
	
	d_reduce = list(map(best_d_reduce, action))  # Default Reduction Table
	r_plane = [
		[decide(i, dr) for i in row]
		for row, dr in zip(action, d_reduce)
	]
	for q,t in nonassoc_errors: r_plane[q][t] = None # These are likely to be one-offs.
	col_class, minimal_cols = find_row_equivalence(zip(*r_plane), None)
	midpoint = list(zip(*minimal_cols))
	# hot = compaction.heavy_rows(midpoint)
	# for r in hot: midpoint[r] = compaction.lighten(midpoint[r])
	row_class, minimal_rows = find_row_equivalence(midpoint, None)
	offset, check = encode_boolean_field_as_offset_check(minimal_rows)
	return {
		'd_reduce': d_reduce,
		'row_class': row_class,
		'col_class': col_class,
		'offset': offset,
		'check': check,
	}
