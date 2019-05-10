"""
The [Pascal grammar](pascal.md) stresses all parts of the parser generator, including all the table
compression bits-and-bobs. Therefore, to get some good confidence that everything works properly,
I went looking for some sample Pascal code on the web. I found it here:

https://www.cs.vassar.edu/~cs331/semantic_actions/testfiles.html -- retrieved 10 May 2019

The main page for the corresponding course is at https://www.cs.vassar.edu/~cs331/

Also on 10 May 2019, I obtained permission via e-mail from [the professor](http://www.cs.vassar.edu/~ide)
to incorporate these samples into the project.

Related idea: This is about the point where you wind up wanting a proper abstract data type for parse nodes.
The object-oriented way to proceed would almost certainly be to build a class hierarchy to represent
different kinds of nodes: semantic analysis and IR-code generation become methods on those classes.
"""

samples = [
"""
program simpleTest (input, output); {Sample tvi code [here](http://www.cs.vassar.edu/~cs331/semantic_actions/examples/simple.tvi)}
var i : integer;
begin
  i := 1
end.
""",

"""
program expressionTest (input, output);   {Sample tvi code [here](http://www.cs.vassar.edu/~cs331/semantic_actions/examples/expression.tvi)}
 var a, b : integer;
        c : real;
 begin
   a := 3;
   b := a * 4;
   c := (b + a)/ 2
 end.
""",

"""
program arrayTest(input, output);    {Sample tvi code here}
var
   m : array[1..5] of integer;
begin
        m[1] := 1;
        m[2] := 2;
        m[3] := 3;
        m[4] := 4;
        m[5] := 5;

        write(m[1]);
        write(m[2]);
        write(m[3]);
        write(m[4]);
        write(m[5])
end.
""",

"""
""",

"""
""",


]

import os
from boozetools import runtime, interfaces
from boozetools.macroparse import compiler

class PascalDriver:
	"""
	This the approach where the parser builds an abstract tree and semantic analysis is done in a separate phase.
	Because this is JUST an example and test-rig for the juicier bits of the parser generator, I'm not going to
	be too picky about abstract data types -- although plans can change.
	"""
	def __init__(self, reserved_words):
		self.reserved = frozenset(reserved_words)
	def scan_ignore(self, yy:interfaces.ScanState, p): pass
	def scan_integer(self, yy:interfaces.ScanState, p): return 'integer', int(yy.matched_text())
	def scan_decimal(self, yy:interfaces.ScanState, p): return 'real', int(yy.matched_text())
	def scan_scientific_notation(self, yy:interfaces.ScanState, p): return 'real', int(yy.matched_text())
	def scan_string_constant(self, yy:interfaces.ScanState, p): return 'string_constant', yy.matched_text()[1:-1].replace("''", "'")
	def scan_relop(self, yy:interfaces.ScanState, p): return 'relop', yy.matched_text()
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
	def parse_parametric_procedure_call(self, name, args): return ('.call.', name, args)



tables = compiler.compile_file(os.path.join(os.path.dirname(__file__), 'pascal.md'))
driver = PascalDriver([T for T in tables['parser']['terminals'] if T.isalpha() and T==T.upper()])
parse = runtime.the_simple_case(tables, driver, driver)

for text in samples:
	if text.strip():
		print(text)
		print("---------------------------------")
		print(parse(text))
		print("=================================")
