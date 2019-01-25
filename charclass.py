"""
In light of unicode support, it's nonsense to work with uncompressed character classes.
Two major categories of operation exist for these things.
The first is logical combination of two character classes to produce a third.
The second is to expand classes into a specific set of include/exclude booleans for
a sorted sequence of bounding points.

I've chosen to define the character-class data structure as a sorted list of lower bounds
with implied exclusion below the first listed bound.
Thus:
"""
import bisect, operator

EMPTY = []
UNIVERSAL = [0]
EOF = [-1, 0]

def in_class(cls:list, codepoint:int) -> bool: return bisect.bisect_right(cls, codepoint) % 2
def singleton(codepoint:int) -> list: return [codepoint, codepoint + 1]
def range_class(first, last) -> list: return [first, last+1] if first <= last else [last, first+1]
def complement(cls:list) -> list:
	if not cls: return UNIVERSAL
	if cls[0]<=0: return cls[1:]
	return [0]+cls
def expand(cls:list, bounds:list):
	""" Given a class and a sorted sequence of codepoints, yield a stream of booleans indicating whether each codepoint is in the class. """
	# It might be simpler to just call 'in_class(...)' in a loop. That would be O(N*log(M)); this is O(N+M).
	# Realistically, the sizes of these things will be small enough to where the simpler approach will be better.
	idx = 0
	for x in bounds:
		while idx<len(cls) and x >= cls[idx]: idx += 1
		yield idx%2
def combine(op, x:list, y:list) -> list:
	""" Arbitrary boolean combination of character classes controlled by 'op :: (bool, bool) -> bool'  """
	result = []
	for b in sorted({0}.union(x, y)): # The zero is included in case op(False, False) == True.
		if len(result) % 2 != bool(op(in_class(x, b), in_class(y, b))):
			result.append(b)
	return result
def union(a:list, b:list) -> list: return combine(operator.or_, a, b)
def intersect(a:list, b:list) -> list: return combine(operator.and_, a, b)
def subtract(a:list, b:list) -> list: return intersect(a, complement(b))