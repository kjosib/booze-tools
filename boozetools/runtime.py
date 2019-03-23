"""
This module is the dual of `compaction.py`:
It provides a runtime interface to compacted scanner and parser tables.
"""

from . import interfaces

class CompactDFA(interfaces.FiniteAutomaton):
	
	def __init__(self, data:dict):
	
	def jam_state(self): return -1
	
	def get_condition(self, condition_name) -> tuple:
		pass
	
	def get_next_state(self, current_state: int, codepoint: int) -> int:
		pass
	
	def get_state_rule_id(self, state_id: int) -> int:
		pass