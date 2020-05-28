from . import interfaces, runtime
from ..scanning import miniscan
from ..parsing import miniparse

class TypicalMiniApp(runtime.AbstractTypical):
	"""
	This class specializes for applications founded on mini-scan and mini-parse,
	to provide reasonable default error handling behavior.
	"""
	
	def __init__(self, *, scan:miniscan.Definition, parse:miniparse.MiniParse):
		hfa, combine = parse.get_hfa_and_combine()
		super().__init__(
			dfa=scan.get_dfa(),
			scan_rules=scan,
			hfa=hfa,
			combine=combine,
		)

