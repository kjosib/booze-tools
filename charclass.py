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
def range_class(first, last) -> list: return [first, last+1] if last > first else [last, first+1]
def complement(cls:list) -> list:
	if not cls: return UNIVERSAL
	if cls[0]<=0: return cls[1:]
	return [0]+cls
def expand(cls:list, bounds:list):
	idx = 0
	for x in bounds:
		while idx<len(cls) and x >= cls[idx]: idx += 1
		yield idx%2
def combine(op, a:list, b:list) -> list:
	bounds = sorted(set(a)|set(b))
	result = []
	for p,x in enumerate(map(op, expand(a, bounds), expand(b, bounds))):
		if len(result)%2 != x: result.append(bounds[p])
	return result
def union(a:list, b:list) -> list: return combine(operator.or_, a, b)
def intersect(a:list, b:list) -> list: return combine(operator.and_, a, b)
def subtract(a:list, b:list) -> list: return intersect(a, complement(b))