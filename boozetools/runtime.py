"""
This module is the dual of `compaction.py`:
It provides a runtime interface to compacted scanner and parser tables.
"""
from boozetools.interfaces import ScanState
from . import interfaces, charclass, algorithms

def sparse_table_function(*, index, data, offset) -> callable:
	"""
	This is meant to illustrate an O(1) mechanism rather than be fast in the specific
	context of Python.
	
	The index and data are collectively a sparse matrix in compressed-sparse-row format.
	The offsets are a pre-computed way to slot that data into a displacement table.
	"""
	width = 1 + max(filter(None, offset)) + max((max(columns) for columns in index if columns))
	table, check = [None]*width, [-1]*width
	
	def init():
		for row_id, columns in enumerate(index):
			displacement = offset[row_id]
			if columns is None:
				assert displacement is None
			elif columns:
				assert displacement >= 0
				for column_id, entry in zip(columns, data[row_id]):
					place = displacement + column_id
					assert 0<=place<width and table[place] is None and check[place] == -1
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
	

def scanner_delta_function(delta) -> callable:
	probe = sparse_table_function(index=delta['index'], data=delta['data'], offset=delta['offset'])
	default = delta['default']
	def fn(state_id:int, symbol_id:int) -> int:
		if state_id<0: return state_id
		q = probe(state_id, symbol_id)
		return fn(default[state_id], symbol_id) if q is None else q
	return fn

def parser_action_function(delta) -> callable:
	probe = sparse_table_function(index=delta['index'], data=delta['data'], offset=delta['offset'])
	default = delta['default']
	def fn(state_id:int, symbol_id:int) -> int:
		q = probe(state_id, symbol_id)
		return default[q] if q is None else q
	return fn


class CompactDFA(interfaces.FiniteAutomaton):
	"""
	This sets up using information
	"""
	def __init__(self, *, dfa:dict, alphabet:dict):
		self.classifier = charclass.MetaClassifier(**alphabet)
		self.delta = scanner_delta_function(dfa['delta'])
		self.initial = dfa['initial']
		self.final = dict(zip(dfa['final'], dfa['rule']))
	
	def jam_state(self): return -1
	def get_condition(self, condition_name) -> tuple: return self.initial[condition_name]
	def get_state_rule_id(self, state_id: int) -> int: return self.final.get(state_id)

	def get_next_state(self, current_state: int, codepoint: int) -> int:
		return self.delta(current_state, self.classifier.classify(codepoint))
	
	
	
class SymbolicRules(interfaces.ScanRules):
	def __init__(self, *, action:dict, driver:object):
		self._message     = action['message']
		self._parameter   = action['parameter']
		self._trail       = action['trail']
		self._line_number = action['line_number']
		self._driver      = driver
		
	def get_trailing_context(self, rule_id: int): return self._trail[rule_id]
	
	def invoke(self, scan_state: ScanState, rule_id:int):
		method = getattr(self._driver, 'on_'+self._message[rule_id])
		method(scan_state, self._parameter[rule_id])
		