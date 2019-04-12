"""
Discarded ideas go here: they may be useful but are far from the simplest possible thing that could work reasonably.
"""


"""
The first such victim is the row-offset method of perfect-hashing.
	* A hash is "perfect" when it requires at most one probe to determine
	the presence or absence of a key; in general these must be precomputed.
	* A hash is "minimal" when (in the lingo of hashing) all the buckets are used.
	* The holy grail of "minimal perfect hashing" generally requires a more complex function.

This is meant to illustrate a possible O(1) mechanism rather than be fast in the specific
context of Python. By sliding the rows of a matrix around, we can find a set of offsets
that leave no column with more than one significant value. That can become a vector of
"data, row_id" pairs (or pair of vectors), along with the vector of row offsets.

"""


def sparse_table_function(*, index, data) -> callable:
	"""
	The index and data are collectively a sparse matrix in compressed-sparse-row format.
	"""
	
	offset = first_fit_decreasing(index)
	width = 1 + max(filter(None, offset)) + max((max(columns) for columns in index if columns))
	table, check = [None] * width, [-1] * width
	
	def init():
		for row_id, columns in enumerate(index):
			displacement = offset[row_id]
			if columns is None:
				assert displacement is None
			elif columns:
				assert displacement >= 0
				for column_id, entry in zip(columns, data[row_id]):
					place = displacement + column_id
					assert 0 <= place < width and table[place] is None and check[place] == -1
					table[place] = entry
					check[place] = row_id
	
	def probe(row_id, column_id):
		displacement = offset[row_id]
		if displacement is None:
			if index[row_id] is None: return data[row_id][column_id]
		else:
			place = displacement + column_id
			if place < width and check[place] == row_id: return table[place]
	
	init()
	return probe


def first_fit_decreasing(indices: list) -> list:
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
	
	def first_fit(row: list) -> int:
		offset = 0
		while any(r + offset in used for r in row): offset += 1
		used.update(r + offset for r in row)
		return offset
	
	displacements = [None] * len(indices)
	for i in sorted([i for i, row in enumerate(indices) if row], key=lambda i: len(indices[i])):
		displacements[i] = first_fit(indices[i])
	print("First-Fit Decreasing Performance vs. CSR:")
	print("   Number of stored values:", len(used))
	print("   Size of wasted space:", max(used) - len(used))
	return displacements


