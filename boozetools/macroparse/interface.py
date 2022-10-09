
from typing import Optional, NamedTuple, Sequence

class ScanAction(NamedTuple):
	""" The information necessary to connect to a driver (presumably) or yield a usable error message. """
	right_context: Optional[int]
	message: Sequence
	line_number: int

