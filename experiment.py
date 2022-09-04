"""
This file is an experimental apparatus.

I wanted to try out a couple different approaches to solving a particular problem.
Specifically: If a state in the ACTION table was coded with a default-reduction,
then knowledge was lost of which cells in that row represent errors. This knowledge
is vitally important for correct operation of the (then-new) error recovery
mechanism. Therefore, it was necessary to find a compact and efficient way to
store this information. This apparatus tries the compression method for several
different grammars and reports on compaction efficacy.
"""
import os, csv
from boozetools.macroparse import compaction


def example(what):
	return os.path.join(os.path.dirname(__file__), 'example', what)

def mmap(op, matrix): return [[op(c) for c in r]for r in matrix]
def msum(matrix): return sum(map(sum, matrix))
def mcount(op, matrix): return msum(mmap(op, matrix))
def mpartial(p, matrix): return mmap(lambda i:i if p(i) else None, matrix)

def is_shift(i): return i > 0
def is_reduce(i): return i < 0
def is_error(i): return i == 0
def care(i): return i is not None

def pic(row, chars:str, on_null='\u25cb'):
	return '|'+''.join(on_null if x is None else chars[x] for x in row)+'|'

def nnot(x): return None if x is None else not x
def lm(fn, *args): return list(map(fn, *args))

def subject(identity):
	print("Subject:", identity)
	with open(example(identity+'.automaton.action.csv')) as fh:
		terminals, *action = (row[2:] for row in csv.reader(fh))
	ROWS, COLS = len(action), len(terminals)
	action = mmap(lambda c:int(c) if c else 0, action)
	FILLED = mcount(bool, action)
	print("Action Table: %d rows * %d cols = %d cells; %d filled (%0.2f%%)"%(ROWS, COLS, ROWS*COLS, FILLED, 100*FILLED/(ROWS*COLS)))
	print("%d shifts, %d reductions, %d errors."%(mcount(is_shift, action), mcount(is_reduce, action), mcount(is_error, action)))
	print("Current Approach:", compaction.measure_approximate_cost(compaction.compress_action_table(action, set())))
	print()


print(__doc__)
subject('pascal')
subject('decaf')
subject('calculator')
subject('json')

