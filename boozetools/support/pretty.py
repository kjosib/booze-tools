""" Bits and bobs in support of visualizing data structures. """
import csv
from itertools import zip_longest

DOT = '\u25cf'

def dotted(rhs, position):
	items = [str(s) for s in rhs]
	items.insert(position, DOT)
	return "[ %s ]"%" ".join(items)


def print_grid(grid):
	lens = list(map(len, grid))
	assert len(set(lens)) == 1, lens
	grid = [[str(cell) for cell in row] for row in grid]
	width = [max(map(len, column)) for column in zip(*grid)]
	horizontal = '\u2500'
	vertical = ' \u2502 '
	upper = horizontal + '\u252c' + horizontal
	inner = horizontal + '\u253c' + horizontal
	lower = horizontal + '\u2534' + horizontal
	# horizontal = '-'
	# vertical = ' | '
	# upper = horizontal + '+' + horizontal
	# inner = horizontal + '+' + horizontal
	# lower = horizontal + '+' + horizontal
	segments = [horizontal*w for w in width]
	divider = inner.join(segments)
	print(upper.join(segments))
	for r, row in enumerate(grid):
		if r %5 == 1: print(divider)
		print(vertical.join(s.rjust(w,' ') for s,w in zip(row, width)))
	print(lower.join(segments))
	
def print_columnar(*columns):
	margin = range(max(map(len, columns)))
	print_grid(list(zip_longest(margin, *columns)))

def write_csv_grid(path, grid):
	with open(path, 'w', newline="") as fh:
		csv.writer(fh).writerows(grid)
