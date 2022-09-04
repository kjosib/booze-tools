"""
Dealing with anything like a programming language, you need a symbol table.
Here's my concept:

I distinguish between:

* name: a distinct sequence of characters with the appearance of a name.
* symbol: an association between name, declaration, definition, namespace, and scope. This association may be a work in progress during certain phases of translation.
* alias: another name for the same symbol, possibly used in a different scope or namespace. (By implication, symbols should record their original names.)
* declaration: something in the text that lets you know a name will be valid, and perhaps a few attributes of its meaning (within some namespace and scope).
* definition: something in the text that tells you exactly what a name means (within a namespace and scope). Normally, whatever you define you implicitly also declare.
* mention: the act of using a name to refer to whatever it signifies, or the place where this is done. In some languages, mentioning a name implicitly declares a corresponding symbol.
* namespace: a particular group of names with similar rules for interpreting them. Names that look the same, but which appear in different namespaces, do not refer to the same thing. Generally something about the local syntax tells you what namespace applies to a name. (For example, in SQL, tables and columns are in separate namespaces.)
* scope: a particular section of text, or of the semantic structure associated with that text. We often think of scope as contiguous and nested, but record-field access is a counterexample. There can be more than one namespace associated with a scope.
* context: the combination of namespace and scope in which some name appears within the text.
* symbol table: the organized collection of all symbols defined or used in the text. The translator may consult or modify the symbol table as needed.
* environment: the slice of the symbol table (and extra related information) in view while translating a particular segment of text.

In this module, I propose a generic structure for symbols, namespaces, and maybe a few other bits.
With luck, it should be suitable for both translation and reasonable error reporting.
One obvious failing is its inherently imperative nature: It relies on mutation.
For the moment, I'll live with that.

I am not concerned with distinguishing between a static and dynamic environment.
Rather, I assume that "the environment" is whatever your application needs for its own interpretive dance.
Thus, the precise structure of "the environment" is not defined here. Your application should define a suitable one.
However, the usual notion is probably that of one or more name-spaces in which the translator might search for
or add names and their definitions.

There are also a few typical patterns of interaction with the environment (and by extension, with namespaces).
The most common are probably:

* adding a name, expecting it not already to exist locally (or at all, if you prohibit shadowing).
* looking up a name, expecting it surely to have an already-associated symbol.
* looking up a name, with the plan to add a fresh symbol locally if one is not found.

The key question is what comes next when an expectation is falsified.
For now, I'll just go with raising an exception.
Why? Because it's Python.

Anyway, you'll probably represent "the environment" as one or more namespaces and maybe some other attributes.
"""

from typing import Optional, Generic, TypeVar

class NoSuchSymbol(KeyError):
	pass

class SymbolAlreadyExists(KeyError):
	pass

T = TypeVar("T")

class NameSpace(Generic[T]):
	"""
	NameSpace bears some resemblance to chainmap with a few extra attributes.
	The "local" is the set of words/names defined in this space.
	The "place" is a general statement of where the namespace "lives", used for error messages.
	The "parent" works like a static link.
	
	What's particularly noteworthy here is the application of static type hinting.
	"""
	def __init__(self, *, place, parent:Optional["NameSpace[T]"]=None):
		self.local : dict[object:T] = {}
		self.place = place
		self.parent : NameSpace[T] = parent
		
	def find(self, key) -> tuple[Optional[T], Optional["NameSpace[T]"]]:
		"""
		Frequently when dealing with nested namespaces in translation,
		you need to know in which layer of the nesting structure a name appears.
		This method usefully returns both the symbol and its host namespace.
		Assuming you've decorated namespace objects to your needs,
		(perhaps via the "place" field)
		you should have no trouble working out e.g. which stack frame you find a variable in.
		In case the symbol is not found, this will return (None, None) for easy procedural testing.
		Why? Because I've
		"""
		if key in self.local:
			return self.local[key], self
		elif self.parent is not None:
			return self.parent.find(key)
		else:
			raise NoSuchSymbol(key)
	
	def replace(self, key, value:T):
		""" Suppose you need to replace a symbol. Fine. But you're going to know it. """
		if key in self.local:
			self.local[key] = value
		else:
			raise NoSuchSymbol(key)
	
	def __getitem__(self, key):
		if key in self.local:
			return self.local[key]
		elif self.parent is not None:
			return self.parent[key]
		else:
			raise NoSuchSymbol(key)
		
	def __contains__(self, key):
		return key in self.local or (self.parent is not None and key in self.parent)
	
	def __setitem__(self, key, value:T):
		if key in self.local:
			raise SymbolAlreadyExists(key)
		else:
			self.local[key] = value

	def new_child(self, place) -> "NameSpace[T]":
		""" Return a subordinate name-space linked to this one. """
		return NameSpace(place=place, parent=self)
