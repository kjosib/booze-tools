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

import collections, operator
from . import foundation as F, pretty

def multi_append(table:dict, row:dict):
	"""
	Utility function for collections of parallel arrays; these often have better
	storage and encoding characteristics than arrays of records do.
	:param table: A dictionary in which several keys point to lists.
	:param row: A dictionary; the values get appended to the corresponding lists in `table`.
	:return: Nothing.
	"""
	for key, value in row.items(): table[key].append(value)

def most_common(row, *, default=0):
	""" Return the most-common element in the array; break ties arbitrarily. """
	C = collections.Counter(row)
	return C.most_common(1)[0][0] if C else default

def is_homogenous(row):
	return len(row) < 2 or all(r == row[0] for r in row)
	
def compress_dfa_matrix(*, initial:dict, matrix:list, final:dict) -> dict:
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
	column_class, minimal_columns = find_row_equivalence(zip(*residue), None)
	residue = list(zip(*minimal_columns))
	for i, row in enumerate(residue): # Taking care to keep rows sparse:
		if sum(map(bool, row)) * 2 > len(row):
			zeros[i], ones[i], residue[i] = ones[i], zeros[i], tuple(None if x is None else int(not x) for x in row)
	row_class, residue = find_row_equivalence(residue, None)
	# Converting the final residue to a set-as-displacement-table representation:
	indices = [[i for i,x in enumerate(row) if x] for row in residue]
	offset, size = first_fit_decreasing(indices, allow_negative=True)
	check = [-1]*size
	for i, (row, base) in enumerate(zip(indices, offset)):
		for col in row:
			check[base+col] = i
	# Tie a pretty bow around it:
	delta = {
		'exceptions': encode_displacement_function(exceptions),
		'background': {
			# For most states, the most common entry is the error transition. Thus: exceptions to that rule:
			'zero': list(zip(*[(index, value) for index, value in enumerate(zeros) if value != -1])),
			'one': ones,
			'row_class': row_class, 'column_class': column_class,
			'offset': offset, 'check': check,
		},
	}
	height, width = len(matrix), len(matrix[0])
	metric = measure_approximate_cost(delta)
	print("DFA matrix was %d rows, %d cols = %d cells; compact form is about %d cells (%0.2f%%)"%(
		height, width, height * width, metric, (100.0*metric/(height*width))
	))
	return {'delta': delta, 'initial': initial, 'final': list(final.keys()), 'rule': list(final.values()),}

def measure_approximate_cost(structure):
	""" Various bits estimate the size of the structures they return. This makes that consistent. """
	if isinstance(structure, (list, tuple)): return 1 + sum(map(measure_approximate_cost, structure))
	elif isinstance(structure, dict): return len(structure) + sum(map(measure_approximate_cost, structure.values()))
	elif isinstance(structure, int) or structure is None: return 1
	else: assert False, type(structure)

def first_fit_decreasing(indices: list, *, allow_negative:bool):
	"""
	(Aho and Ulman [2]) and (Ziegler [7]) advocate this scheme...
	This function finds a set of displacements such that no two index[i][j]+displacement[i] are the same.
	The entry in list `indices` may be a list of columns within a given row which are considered to
	have legitimate data in some particular sparse matrix. But note that in Python, dictionaries iterate
	as their keys, so there's a shortcut...

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
	"""
	used = set()
	def first_fit(row: list) -> int:
		if not row: return 0
		offset = 0 - min(row) if allow_negative else 0
		while any(r + offset in used for r in row): offset += 1
		used.update(r + offset for r in row)
		return offset
	
	displacements = [0] * len(indices)
	for i in F.grade(list(map(len, indices)), descending=True): displacements[i] = first_fit(indices[i])
	size = max(used)+1 if used else 0
	print("First-Fit Decreasing placed %d entries among %d positions."%(len(used), size))
	return displacements, size

def encode_displacement_function(exceptions:list):
	"""
	This builds a typical textbook-style displacement table: a simple kind of perfect-hash,
	which may not be minimal but it's usually decently close.
	:param exceptions: a list of dictionaries; keys are column numbers, values are destination state numbers.
	No attempt is made to coalesce similar or identical rows here:
		(1) It's the caller's responsibility.
		(2) Only the caller knows the best way to perform such a feat.
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

def decompose_by_default_reduction(matrix:list, essential_errors:set):
	"""
	The first phase of compacting a parser's "ACTION" table
	:param matrix:
	:param essential_errors:
	:return: default-reduction vector and resiude matrix where allowed entries have been turned to `None`.
	"""
	reduce = [most_common([a for a in row if a < 0]) for row in matrix] # Default Reduction Table
	residue = [[
		value if (q,column) in essential_errors or value not in (0, default) else None
		for column, value in enumerate(row)
	] for q, (row, default) in enumerate(zip(matrix, reduce))]
	return reduce, residue

def decompose_by_edit_distance(matrix):
	"""
	Note that you CAN get a value of `None` in an 'edit' resulting from this function.
	Since null means "use the default reduction" in this context, that's considered OK.
	In a bare-metal implementation, we might decide actually to establish a "rule" for
	the error response activity: it would therefore get its own number (perhaps -1)
	and the associated code would be responsible for any error processing. That would
	take away some of the special-casing associated with parse errors: you just need
	to make sure the correct code reference is installed in the rule response table.
	"""
	height, width = len(matrix), len(matrix[0])
	population = [width - row.count(None) for row in matrix]
	schedule = F.grade(population)
	fallback = [-1] * height
	for count, q in enumerate(schedule):
		metric = population[q]
		for j in schedule[:count]:
			edit_distance = sum( a != b for a, b in zip(matrix[q], matrix[j]))
			if edit_distance < metric: metric, fallback[q] = edit_distance, j
	# Now that we have our fallback vector computed, it's straightforward to work out the edits:
	def edits(row, basis) -> dict:
		if basis < 0: return {c:v for c,v in enumerate(row) if v is not None}
		else: return {c:v for c,(x,v) in enumerate(zip(matrix[basis], row)) if x!=v}
	return fallback, [edits(row, basis) for row, basis in zip(matrix, fallback)]

def compress_action_table(matrix:list, essential_errors:set) -> dict:
	"""
	Produce a compact representation of the "ACTION" table for a typical shift-reduce parser.
	:param matrix: list-of-lists of parse actions: positive numbers are shifts; negative are reductions, zero is error.
	:param essential_errors: set of pairs of (state_id, terminal_id) which MUST NOT go to a default reduction.
	:return: a compact structure.
	"""
	height, width = len(matrix), len(matrix[0]) # Stats for comparison to the compression method
	reduce, residue = decompose_by_default_reduction(matrix, essential_errors)
	fallback, edits = decompose_by_edit_distance(residue)
	edit_table = encode_displacement_function(edits)
	for q, (f, e) in enumerate(zip(fallback, edits)):
		if f == -1 and not e: # Think about it. This EXACTLY selects default-reduce-only states.
			edit_table['offset'][q] = len(edit_table['check']) # This marks it as an interactive state.
	result = {'reduce': reduce, 'fallback': fallback, 'edits': edit_table,}
	metric = measure_approximate_cost(result)
	print("Action matrix was %d * %d = %d; compressed to %d (%0.2f%%)"%(
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
		if is_homogenous(vector): return vector[0]
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
	col_class_offset = F.everted(F.grade([vector.count(0) for vector in minimal_columns]))
	minimal_rows = [{col_class_offset[c]:x for c, x in enumerate(row) if x} for row in zip(*minimal_columns)]
	row_class_offset, size = first_fit_decreasing(minimal_rows, allow_negative=False)
	residue = [0]*size
	for r_off, row in zip(row_class_offset, minimal_rows):
		for c_off, value in row.items():
			if value: residue[r_off+c_off] = value
	
	# Fill the holes in the foo_index vectors accordingly:
	for cls_id, state_id in zip(row_class, row_residue):
		row_index[state_id] = row_class_offset[cls_id] + hi_water_mark
	for cls_id, nonterm_id in zip(col_class, column_residue):
		col_index[nonterm_id] = col_class_offset[cls_id] + hi_water_mark
	
	# Wrap up and return.
	print("GOTO table original size: %d rows, %d columns -> %d cells"%(height, width, height * width))
	result = {'row_index': row_index, 'col_index': col_index, 'quotient': quotient+residue, 'mark': hi_water_mark}
	metric = measure_approximate_cost(result)
	print("GOTO compact size: %d (%.2f%%)"%(metric, 100.0*metric/(height * width)))
	return result

def find_row_equivalence(matrix, do_not_care):
	"""
	This typically gets called twice per matrix with a transposition for the columns.
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
			index.append(F.allocate(classes, list(row)))
	return index, classes

