from .lalr import lalr_construction
from .lr1 import canonical_lr1, minimal_lr1


PARSE_TABLE_METHODS = {
	'LALR': lalr_construction,
	'CLR': canonical_lr1,
	'LR1': minimal_lr1,
}

