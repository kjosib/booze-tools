"""
This module implements the macro-enabled enhanced-BNF context-free grammar semantics.
There is exactly zero concern for where the production rules come from.

Because the production rules support a no-kidding macro language, this module gets a
good bit of hair all by itself.

The MetaParse definition object works with structured rewriting-rule objects, so this
file begins with definitions of some semantic objects. Next come a grammar and scanner
(implented via the "mini" infrastucture) which build those semantics up. Last is a
class definition for a grammar object which supplies the necessary bits to make
the extensions over BNF work properly.
"""

from .. import context_free, miniparse, miniscan, algorithms

class DefinitionError(Exception): pass

### Semantic categories for the breakdown of rewrite rules:
class Element:
	"""
	Base class of RHS elements.
	What you do NOT see here is reflected in the constructor for class Rewrite:
		Specifically, any Element may have a 'capture' attribute added; this makes the value
		available to any action to its right.
		Please note: 'capturing' a rule-final action makes no sense and is presently ignored.
	"""
	def canonical_symbol(self, bindings:dict) -> str:
		""" To support the enhancements over plain BNF, each element needs a canonical symbolic expression. """
		raise NotImplementedError(type(self))

class Action(Element):
	def __init__(self, name): self.name = name
	def canonical_symbol(self, bindings:dict) -> str: return ':'+self.name # Maybe I could pass actions into macros by adjusting this?

class Symbol(Element):
	def __init__(self, name): self.name = name
	def canonical_symbol(self, bindings:dict) -> str: return bindings.get(self.name, self.name)

class InlineRenaming(Element):
	def __init__(self, alternatives):
		self.alternatives = tuple(alternatives)
		for a in self.alternatives: assert isinstance(a, Element) and not isinstance(a, Action)
		
	def canonical_symbol(self, bindings:dict) -> str: return "[%s]"%("|".join(s.canonical_symbol(bindings) for s in self.alternatives))

class MacroCall(Element):
	def __init__(self, name, actual_parameters):
		self.name, self.actual_parameters = name, tuple(actual_parameters)
		assert isinstance(self.name, str)
		for a in self.actual_parameters: assert isinstance(a, Element), type(a)
	def canonical_symbol(self, bindings:dict) -> str: return "%s(%s)"%(self.name, ",".join(s.canonical_symbol(bindings) for s in self.actual_parameters))


class Rewrite:
	def __init__(self, elements:list, precsym:str=None):
		self.elements = elements
		self.precsym = precsym
		self.message:Action = self.elements.pop(-1) if isinstance(self.elements[-1], Action) else None
		self.__args = args = []
		self.size = len(self.elements)
		for i,elt in enumerate(self.elements):
			if hasattr(elt, 'capture'): args.append(i)
		if not args: args.extend(range(self.size)) # Pick up everything if nothing is special.
	def prefix_capture(self, size:int):
		return tuple(c - size for c in self.__args if c < size)

"""
The MacroParse metagrammar contains various repetition constructs. The following functions
act as rudimentary macros to relieve some redundancy; they essentially mean something like:

	list_of(what, sep) -> what :first | .list_of(what, sep) sep .what :append
	one_or_more(what) -> what :first | .one_or_more(what) .what :append

Doing macros for real is a little more complicated and will be dealt with further down.
"""
def list_of(what, sep):
	head = 'list_of(%r,%r)'%(what,sep)
	PRODUCTION.rule(head, '.%s'%what)(FIRST)
	PRODUCTION.rule(head, '.%s %s .%s'%(head, sep, what) )(APPEND)
	return head
def one_or_more(what):
	head = 'one_or_more(%r)' % (what)
	PRODUCTION.rule(head, '.%s' % what)(FIRST)
	PRODUCTION.rule(head, '.%s .%s' % (head, what))(APPEND)
	return head
def FIRST(element): return [element]
def APPEND(the_list, element):
	the_list.append(element)
	return the_list


### The MacroParse metagrammar for individual production lines is as follows.
PRODUCTION = miniparse.MiniParse('production')

PRODUCTION.rule('production', '.head .'+list_of('rewrite', '|'))(None)

PRODUCTION.rule('head', '|')(None) # "use prior" is represented by a null "head".
PRODUCTION.rule('head', '.name arrow',)(None) # This will come across as a string.
PRODUCTION.rule('head', '.name ( .%s ) arrow'%list_of('name', ','))(None) # Represent macro heads with (name, args) tuples.

ELEMENTS = one_or_more('element')
PRODUCTION.rule('rewrite', ELEMENTS)(Rewrite)
PRODUCTION.rule('rewrite', '.'+ELEMENTS+' pragma_precsym .terminal')(Rewrite)

PRODUCTION.renaming('terminal', 'name', 'literal')

PRODUCTION.renaming('element', 'positional_element')
@PRODUCTION.rule('element', 'capture .positional_element')
def capture(positional_element:Element) -> Element:
	positional_element.capture = True
	return positional_element

PRODUCTION.renaming('positional_element', 'actual_parameter')
PRODUCTION.rule('positional_element', 'message')(Action)

PRODUCTION.renaming('actual_parameter', 'symbol') # alternation brackets should not nest directly...
PRODUCTION.rule('actual_parameter', '[ .'+one_or_more('symbol')+' ]')(InlineRenaming)

PRODUCTION.rule('symbol', 'name')(Symbol)    # Normal symbol
PRODUCTION.rule('symbol', 'literal')(Symbol) # Also a normal symbol with a funny name
PRODUCTION.rule('symbol', '.name ( .'+list_of('actual_parameter', ',')+' )')(MacroCall)


### The lexeme definitions for production rule lines are as follows:
LEX = miniscan.Definition()
LEX.on(r'\s+')(None) # Ignore whitespace
LEX.on(r'\l\w*')('name') # Identifiers as token type "name".
LEX.on(r':\l\w*')(lambda scanner:('message', scanner.matched_text()[1:])) # Strip out the colon for message names
LEX.on(r'%\l+')(lambda scanner:('pragma_'+scanner.matched_text()[1:], None)) # Build pragma token types from the text.
LEX.on(r'[.]/\S')('capture') # a dot prefixes a captured element, so it needs to be followed by something.
LEX.on(r'[][(),|]')(lambda scanner:(scanner.matched_text(), None)) # Punctuation is represented directly, with null semantic value.
LEX.on(r"'\S+'")(lambda scanner:('literal', scanner.matched_text()[1:-1])) # Literals are allowed two ways, so you can
LEX.on(r'"\S+"')(lambda scanner:('literal', scanner.matched_text()[1:-1])) # easily contain whichever kind of quote.
LEX.on(r'[-=>:<]+')('arrow') # Arrows in grammar definitions tend to look all different ways. This is flexible.


class MacroDefinition:
	def __init__(self, name:str, formals, line_nr:int):
		self.name = name
		self.formals = tuple(formals)
		self.line_nr = line_nr
		self.rewrites = []
		self.actually_used = False
		if len(set(self.formals) | {name}) <= len(self.formals): raise DefinitionError("On line %d, all the names in a macro head declaration must be distinct."%line_nr)

### Grammar object:
# Please note: The format of an action entry shall be the tuple <message_name, tuple-of-offsets, line_number>.
# These are a pass-through into the ContextFreeGrammar and eventually the parse tables themselves.

def illustrate_position(line:str, column:int): return line[:column]+'<<_here_>>'+line[column:]

class EBNF_Definition:
	def __init__(self):
		self.plain_cfg = context_free.ContextFreeGrammar()
		self.current_head = None # This bit of state facilitates the feature of beginning a line with an alternation symbol.
		self.start = [] # The correct start symbol(s) may be specified asynchronously to construction or the rules.
		self.inferential_start = None # Use this to infer a start symbol if necessary.
		self.macro_definitions = {} # name -> MacroDefinition
		self.implementations = {} # canonical symbol -> line number of first elaboration
		self.current_line_nr = 0 # Useful in diagnostic messages.
	
	def gripe(self, message): raise DefinitionError('At line %d: %s.'%(self.current_line_nr, message))
	
	def read_one_line(self, line:str, line_nr:int):
		""" This is the main interface to defining grammars. Call this repeatedly for each line of the grammar. """
		assert isinstance(line_nr, int), type(line_nr)
		self.current_line_nr = line_nr
		metascan = LEX.scan(line)
		try: head, rewrites = PRODUCTION.parse(metascan)
		except algorithms.ScanError as e:
			column = e.args[0]
			self.gripe('The MacroParse MetaScanner got confused right...\n\t'+illustrate_position(line, column))
		except algorithms.ParseError as e:
			self.gripe('The MacroParse MetaParser got confused. Stack condition was\n\t%r %s %r\nActual point of failure was:\n\t%s'%(e.args[0],context_free.DOT, e.args[1], illustrate_position(line, metascan.current_position())))
		del metascan
		# Set the current head field, or use it unchanged if not specified on this line:
		if head is None:
			if self.current_head is None:
				self.gripe('Confused about what the current head nonterminal is')
			head = self.current_head
		else:
			if isinstance(head, tuple): # Do we need to enter a macro declaration?
				name, formals = head
				if name in self.macro_definitions: # Prevent re-declarations.
					raise DefinitionError('Macro %r initially declared on line %d; please do not redeclare on line %d.'%(name, self.macro_definitions[name].line_nr, line_nr))
				else: head = self.macro_definitions[name] = MacroDefinition(name, formals, line_nr)
			self.current_head = head
		# Proceed to do the right thing with supplied rewrite rules on this line:
		if isinstance(self.current_head, MacroDefinition):
			self.current_head.rewrites.extend(rewrites)
		else:
			assert isinstance(head, str)
			if self.inferential_start is None: self.inferential_start = head
			for R in rewrites: self.__install(head, R, {})
		pass
	
	def __install(self, head:str, rewrite:Rewrite, bindings:dict):
		"""
		Install one rewrite rule:
		Does everything necessary to interpret extension forms down to plain BNF,
		and then enters that into self.plain_bnf as an option for `head`.
		"""
		raw_bnf = [self.__desugar(E, rewrite, i, bindings) for i, E in enumerate(rewrite.elements)]
		raw_message = None if rewrite.message is None else rewrite.message.canonical_symbol(bindings)
		if len(raw_bnf) == 1 and raw_message is None: attribute = None
		else:
			offsets = rewrite.prefix_capture(len(raw_bnf))
			attribute = (raw_message, offsets, self.current_line_nr)
		self.plain_cfg.rule(head, raw_bnf, attribute, rewrite.precsym)
	
	def __desugar(self, element:Element, rewrite:Rewrite, position:int, bindings:dict) -> str:
		"""
		This is basically a case-statement over the types of symbols that may appear in a right-hand side.
		It needs to make sure that compound (a.k.a. extended) symbols are properly defined (once) in plain
		BNF before they get used in a real rule. As such, it contains the core of the macro system.
		"""
		canon = element.canonical_symbol(bindings)
		if isinstance(element, Symbol):
			return canon
		elif isinstance(element, Action):
			if canon in self.implementations: self.gripe('Internal action %s was first elaborated on line %d; reuse is not (presently) supported.'%(canon, self.implementations[canon]))
			self.implementations[canon] = self.current_line_nr
			attribute = (canon, rewrite.prefix_capture(position), self.current_line_nr)
			self.plain_cfg.rule(canon, [], attribute, None)
			return canon
		elif isinstance(element, InlineRenaming):
			if canon not in self.implementations:
				self.implementations[canon] = self.current_line_nr
				for a in element.alternatives: self.plain_cfg.rule(canon, [self.__desugar(a, None, None, bindings)], None, None)
			return canon
		elif isinstance(element, MacroCall):
			if canon not in self.implementations:
				self.implementations[canon] = self.current_line_nr
				# Construct a new binding environment; lexical scope...
				try: definition = self.macro_definitions[element.name]
				except KeyError: self.gripe('Macro call %s is not yet defined. Please define macros before using them. (This limitation may eventually be lifted.)'%element.name)
				assert isinstance(definition, MacroDefinition)
				definition.actually_used = True
				actual_parameters = [self.__desugar(p, None, None, bindings) for p in element.actual_parameters]
				if len(actual_parameters) != len(definition.formals): self.gripe("Macro call %s has %d parameters; expected %d."%(element.name, len(actual_parameters), len(definition.formals)))
				new_bindings = dict(zip(definition.formals, actual_parameters))
				for r in definition.rewrites:
					assert isinstance(r, Rewrite)
					self.__install(canon, r, new_bindings)
			return canon
		
		assert False, 'Not finished handling %r.'%type(element)
	
	def validate(self):
		unused_macros = sorted(name+':'+str(definition.line_nr) for name, definition in self.macro_definitions.items() if not definition.actually_used)
		if unused_macros: self.gripe('The following macro(s) were defined but never used: '+', '.join(unused_macros))
		if not self.inferential_start: self.gripe("No production rules have been given, so how am I to compile a grammar? (You could give a trivial one...)")
		if not self.start:
			print('Inferring CFG start symbol %r from earliest production because none was given explicitly.'%self.inferential_start)
			self.start.append(self.inferential_start)
		self.plain_cfg.validate(self.start)
		
			