"""
Even for the most basic unicode support, it's nonsense to work with uncompressed character sets.

As a first (effective, but unicode-naive) approach to working with sets of characters in compact
form, I've chosen to define the character-class data structure as a sorted list of lower bounds
with implied exclusion below the first listed bound. That is: a character is a member of
the class exactly when an odd number of lower-bounds in the class are less-than-or-equal-to
that character's codepoint value. (See the `in_class(...)` function.)

Two major categories of operation exist for these things.

	The first is logical combination of two sets of characters to produce a third.
	The second is to expand classes into a specific set of include/exclude booleans for
	a sorted sequence of bounding points.
	
	The next segment provides for the manufacture of character classes idiomatically:
	singletons, ranges, and logical combinations (set operations).

Of note, I treat -1 as the "end-of-file" character to make end-of-file rule processing
blend in with the rest of the finite-automaton clockwork, but it is a bit special:
"end-of-file" does not appear in the 'universal set' of characters or the complement
of any class, so the only way to get it is expressly from an end-of-file rule or end-of-line
trailing-context. This has implications for how set complements should be constructed.

Lower down in the file, I define standard POSIX-type character classes for the ASCII range.

Note that locale-based POSIX character equivalents are not supported in this module.
Digraphs (e.g. Czech or Spanish "ch") mean the concept works at a higher level than
the individual code point, and would throw several things out of kilter.

It turns out that true unicode character classes (UCCs) have lots and lots and LOTS of
codepoint boundaries, so that it's impractical to use the above idea for supporting
unicode with any sophistication. That calls for a different approach.

Ideally most of the Finite Automaton machinery would be insulated from changes in support
of Smart Unicode Mode. There are certain -- challenges.

"""
import bisect, operator

# How to tell if a character (by codepoint) is a member of the class:
def in_class(cls:list, codepoint:int) -> bool: return bisect.bisect_right(cls, codepoint) % 2


# Character class construction and set-operations:
EMPTY = []
UNIVERSAL = [0]
EOF = [-1, 0]

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

# POSIX classes for the ASCII range:
# (See https://www.regular-expressions.info/posixbrackets.html)

POSIX = {}
POSIX['ascii'] = range_class(0, 127)
POSIX['cntrl'] = union(range_class(0, 31), singleton(127))
POSIX['blank'] = union(singleton(9), singleton(32))
POSIX['space'] = union(range_class(9, 13), singleton(32))
POSIX['digit'] = range_class(ord('0'), ord('9'))
POSIX['upper'] = range_class(ord('A'), ord('Z'))
POSIX['lower'] = range_class(ord('a'), ord('z'))
POSIX['alpha'] = union(POSIX['upper'],  POSIX['lower'])
POSIX['alnum'] = union(POSIX['digit'], POSIX['alpha'])
POSIX['word']  = union(POSIX['alnum'], singleton(ord('_')))
POSIX['xdigit'] = union(POSIX['digit'], union(range_class(ord('A'), ord('F')), range_class(ord('a'), ord('f'))))
POSIX['print'] = subtract(POSIX['ascii'], POSIX['cntrl'])
POSIX['graph'] = subtract(POSIX['print'], POSIX['space'])
POSIX['punct'] = subtract(POSIX['graph'], POSIX['alnum'])

assert all(cls == sorted(cls) for cls in POSIX.values())


# To the POSIX classes I add a number of additional definitions:
mode_ascii = dict(POSIX)
def _init_():
	low_ASCII_names = 'NUL SOH STX ETX EOT ENQ ACK BEL BS TAB LF VT FF CR SO SI DLE DC1 DC2 DC3 DC4 NAK SYN ETB CAN EM SUB ESC FS GS RS US SP'.split()
	mode_ascii.update((char, singleton(codepoint)) for codepoint, char in [
		(0, '0'), (27, 'e'), (127, 'DEL'),
		*enumerate('abtnvfr', 7),
		*enumerate(low_ASCII_names),
	])
	mode_ascii['ANY'] = UNIVERSAL
	mode_ascii['vertical'] = range_class(10, 13)
	mode_ascii['DOT'] = complement(mode_ascii['vertical'])
	mode_ascii['horizontal'] = union(range_class(8, 9), singleton(32))
	for shorthand, longhand in [
		('d', 'digit'),
		('l', 'alpha'),
		('w', 'word'),
		('s', 'space'),
		('h', 'horizontal'),
	]:
		mode_ascii[shorthand] = mode_ascii[longhand]
		mode_ascii[shorthand.upper()] = subtract(mode_ascii['DOT'], mode_ascii[longhand])


_init_()
