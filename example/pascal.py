"""
This driver application actually exists as a bizarrely-bulky test rig for one aspect of the
most recent GOTO-table compression function. Also, it shows that the Pascal grammar definition
file nicely describes the sample Pascal programs in this folder.

Easy exercise for the reader: There are more example pascal programs at
	http://sandbox.mc.edu/~bennet/cs404/doc/pasdex.html
Finish the driver to be able to parse all of these. Note: one of these is a UNIT definition,
which requires some additional production rules.

Moderate exercise: Make the parser generate a nicer abstract syntax tree that you can walk.
Implement and test a routine that displays a nice data-dump of such a tree.

Vigorous exercise: Take the above abstract syntax trees and transcode them into Ansi C,
taking care of semantic differences between otherwise-similar forms. Such code is likely
to be ugly and misshapen, but it should run just fine. In particular, proper support for
nested-function scopes will require special care with the calling convention.

Strenuous exercise: Instead of building C code (structure of which is largely isomorphic)
build (not-optimized) assembler code for NASM or a CPU simulator of your choice. Assume
the result will be linked against a convenient runtime library for your platform.
"""

import os
from boozetools import runtime, interfaces
from boozetools.macroparse import compiler

class PascalDriver:
	"""
	This the approach where the parser builds an abstract tree and semantic analysis is done in a separate phase.
	Because this is JUST an example and test-rig for the juicier bits of the parser generator, I'm not going to
	be too picky about abstract data types -- although plans can change.
	
	As mentioned in the definition file, the set of reserved words is recovered from the set of terminals.
	This driver's constructor accepts that set as a parameter.
	
	Related idea: This is about the point where you wind up wanting a proper abstract data type for parse nodes.
	The object-oriented way to proceed would almost certainly be to build a class hierarchy to represent
	different kinds of nodes: semantic analysis and IR-code generation become methods on those classes.
	"""
	def __init__(self, reserved_words): self.reserved = frozenset(reserved_words)
	def scan_ignore(self, yy:interfaces.ScanState, p): pass
	def scan_unterminated_comment(self, yy:interfaces.ScanState, p):
		raise interfaces.ScanError(yy.current_position(), 'unterminated comment')
	def scan_integer(self, yy:interfaces.ScanState, p): return 'integer', int(yy.matched_text())
	def scan_decimal(self, yy:interfaces.ScanState, p): return 'real', float(yy.matched_text())
	def scan_scientific_notation(self, yy:interfaces.ScanState, p): return 'real', float(yy.matched_text())
	def scan_string_constant(self, yy:interfaces.ScanState, p):
		return 'string_constant', yy.matched_text()[1:-1].replace("''", "'")
	def scan_identifier(self, yy:interfaces.ScanState, p): return 'identifier', yy.matched_text()
	def scan_word(self, yy:interfaces.ScanState, p):
		# Checks a table of reserved words.
		word = yy.matched_text().upper()
		if word in self.reserved: return word, None
		else: return 'identifier', word
	def scan_token(self, yy:interfaces.ScanState, p):
		text = yy.matched_text()
		return text, text
	
	def parse_first(self, item): return [item]
	def parse_append(self, the_list, item):
		the_list.append(item)
		return the_list
	def parse_empty(self): return ()
	def parse_assignment(self, lhs, rhs):
		return ('assign', lhs, rhs)
	def parse_plain_stmt(self, command): return command
	def parse_labeled_stmt(self, label_nr, command): return ('@'+str(label_nr)+':', command)
	def parse_product(self, lhs, op, rhs): return (op, lhs, rhs)
	def parse_sum(self, lhs, op, rhs): return (op, lhs, rhs)
	def parse_array_type(self, range, domain): return ('ARRAY', range, domain)
	def parse_array_element(self, lhs, index): return ('.index.', lhs, index)
	def parse_parametric_procedure_call(self, name, args): return ('.pcall.', name, args)
	def parse_naked_procedure_call(self, name): return ('.pcall.', name, ())
	def parse_parametric_function_call(self, name, args): return ('.fcall.', name, args)
	# There is no rule for a naked function call; you have to notice in the symbol table.
	# This same logic COULD be applied to the concept of a naked procedure call, but having
	# it in the grammar seemed like a good idea.
	def parse_relational_test(self, lhs, relop, rhs): return ('.test.', lhs, relop, rhs)
	def parse_if_then(self, test, if_true): return ('.if.', test, if_true)
	def parse_if_then_else(self, test, if_true, if_false): return ('.ifelse.', test, if_true, if_false)
	def parse_normal_args(self, names, type_id): return ('.args.', names, type_id)
	def parse_sequence(self, sequence): return ('.seq.', *sequence)
	def parse_while_loop(self, test, stmt): return ('.while.', test, stmt)
	def parse_negate(self, item):
		if isinstance(item, (int, float)): return 0-item
		else: return ('.neg.', item)


# Similar to what's done in the calculator example, this reads and compiles the grammar every time.
definition_path = os.path.join(os.path.dirname(__file__), 'pascal.md')
tables = compiler.compile_file(definition_path)  # or maybe: json.load('pascal.automaton')
# As mentioned in the definition file, the all-upper-case terminals are reserved words.
driver = PascalDriver([T for T in tables['parser']['terminals'] if T.isalpha() and T==T.upper()])
parse = runtime.the_simple_case(tables, driver, driver)

print("=====================")
with open(os.path.join(os.path.dirname(__file__), 'pascal.pas')) as fh:
	samples = fh.read().split('####')
for text in samples:
	text = text.strip()
	if text:
		try: print(parse(text)[0])
		except interfaces.ParseError as e:
			print("Parse error at token:", repr(e.args[1]))
			print('Parser stack looks like:')
			print('\t'+' '.join(e.args[0]))
			exit(1)
		except interfaces.ScanError as e:
			print("Scan error %r at character %d"%(e.args[1], e.args[0]))
			exit(1)
print("=====================")
print("Everything parsed OK.")