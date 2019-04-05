"""========================================================================================================
This is a sample desktop-calculator program to demonstrate using a MacroParse language definition
in a proper application. It is not the only way, and it is not the most efficient way, but it does
exercise the bits.

A nice exercise-for-the-reader would be to add a facility for defining functions, and perhaps
preload said facility with some built-in functions from the math library.

Type the word "quit"  on a line by itself (or finish stdin -- ^Z on Dos, ^D on Unix) to end this program.
The question mark '?' repeats this message and displays the current values of variables.
Otherwise, arithmetic expressions (+-*/^) are evaluated and printed. Values may be assigned to
variables with the '=' sign.

"""
import operator, math, os
from boozetools import runtime, interfaces
from boozetools.macroparse import compiler

class CalculatorDriver:
	"""
	This is relatively simple, but it does demonstrate a persistent memory.
	"""
	def __init__(self):
		self.memory = {'e':math.e, 'pi':math.pi, 'i':1j} # Pre-load few useful values...
		self.parse_add = operator.add
		self.parse_subtract = operator.sub
		self.parse_multiply = operator.mul
		self.parse_divide = operator.truediv
		self.parse_power = operator.pow
		self.parse_negate = operator.neg
		self.parse_lookup = self.memory.__getitem__
	def scan_ignore_whitespace(self, yy:interfaces.ScanState, parameter): pass
	def scan_punctuation(self, yy:interfaces.ScanState, parameter): return yy.matched_text(), None
	def scan_real(self, yy:interfaces.ScanState, parameter): return 'number', float(yy.matched_text())
	def scan_imaginary(self, yy:interfaces.ScanState, parameter): return 'number', float(yy.matched_text()[:-1])*1j
	def scan_variable(self, yy:interfaces.ScanState, parameter): return 'variable', yy.matched_text()
	def parse_evaluate(self, value):
		print(" -->",value)
		return value
	def parse_assign(self, name, value):
		self.memory[name] = value
		print(name, '=', value)
		return value
	def parse_help(self, _):
		print(__doc__)
		print(self.memory)

tables = compiler.compile_file(os.path.join(os.path.dirname(__file__), 'calculator.md'))
driver = CalculatorDriver()
parse = runtime.the_simple_case(tables, driver, driver)

def main():
	import sys
	driver.parse_help(None)
	for line in sys.stdin:
		if line.strip().lower() == 'quit': break
		if line.strip():
			try: parse(line.strip())
			except KeyError: print("-- OCH! No such variable. --")
			except interfaces.LanguageError: print('-- Not quite sure what that means. Sorry. --')
	
if __name__ == '__main__': main()
