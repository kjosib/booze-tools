""" How to build a workbench when you don't have a workbench to build it with... """

import regular, miniparse, algorithms, charclass

ASCII_CONTROL = {i:s for s,i in enumerate('NUL SOH STX ETX EOT ENQ ACK BEL BS TAB LF VT FF CR SO SI DLE DC1 DC2 DC3 DC4 NAK SYN ETB CAN EM SUB ESC FS GS RS US SP'.split())}
ASCII_CONTROL['DEL'] = 127

ESCAPE = {x:c for c, x in enumerate('abtnvfr',7)}
ESCAPE.update({'0' : 0,'e' : 27,})


rex = miniparse.MiniParse('Pattern')


SHORTHAND = {}
for c, expr in [
	('d', r'[0-9]'),
	('D', r'[^\d]'),
	('h', r'[\dA-Fa-f]'),
	('H', r'[^\h]'),
	('s', r'[ \t\r\n\f\v]'),
	('S', r'[^\s]'),
	('w', r'[A-Za-z_]'),
	('W', r'[^\w]'),
]: SHORTHAND[c] = rex.parse(bootstrap_scan(expr))

