"""
Trees, version two.

The current implemented notion is that the tree contains only the tree; semantic data is separate.
Practical tree-passes descend from `class TreePass` and expose attributes to describe semantic values.
This is still far from the final form, but it has enabled some interesting discoveries.
"""

import abc

class RankedAlphabet:
	"""
	A ranked alphabet is a couple (F,Arity) where F is a finite set and Arity is a mapping from F into N.
		-- TATA, page 15.
	
	This version compels symbols to be categorized (many-to-many) to the extent they'll be used for anything.
	I don't yet bother with a notion of meta-variables.
	"""
	
	def __init__(self, *categories:str):
		self.__categories = {c:set() for c in categories}
		assert all(c.isidentifier() for c in categories)
		self.__symbols = {}
	
	def __getitem__(self, item):
		return self.__symbols[item]
		
	def categorize(self, category_name, *symbol_names):
		""" Declares membership of symbols in categories. Contributes to the run-time validation layer. """
		self.__categories[category_name].update(self.__symbols[s] for s in symbol_names)
		
	def symbol(self, name:str, *categories:str, **slots) -> type:
		"""
		This function creates/registers a new type of symbol as a Python class derived from BaseTerm (below).
		Keyword-arguments are field-name = category-name, except that category-names can have a multiplicity suffix.
		The suffixes are just the ordinary ? * + characters understood from regular expressions.
		Constructing an instance will assert that it's been constructed from the correct field types.
		Optional fields can be None. Multiple fields should be a list or tuple.
		"""
		
		def make_check(cat:str):
			if cat.endswith('?'): return _check_optional(self.__categories[cat[:-1]])
			elif cat.endswith("*"): return _check_zero_or_more(self.__categories[cat[:-1]])
			elif cat.endswith("+"): return _check_one_or_more(self.__categories[cat[:-1]])
			else: return _check_one(self.__categories[cat])
		
		assert name not in self.__symbols
		assert name.isidentifier()  # Keep this; we dispatch to methods by these names.
		it = self.__symbols[name] = type(name, (BaseTerm,), {
			"__slots__": tuple(slots.keys()),
			"_arity_": len(slots),
			"_type_predicates_": tuple(make_check(cat) for cat in slots.values()),
			"_appearance_": '<%s/%d>'%(name,len(slots)),
			"_alphabet_":self,
		})
		for c in categories:
			self.__categories[c].add(it)
		return it
	
def _check_one(category): return lambda x: type(x) in category
def _check_one_or_more(category): return lambda xs: xs and all(type(x) in category for x in xs)
def _check_zero_or_more(category): return lambda xs: all(type(x) in category for x in xs)
def _check_optional(category): return lambda x: x is None or type(x) in category


class BaseTerm:
	"""
	Thus, a term t ∈ T(F,X) may be viewed as a finite ordered ranked tree,
	the leaves of which are labeled with variables or constant symbols and
	the internal nodes are labeled with symbols of positive arity, with
	out-degree equal to the arity of the label...
		-- TATA, page 15.
	
	We confuse terms and trees...
		-- TATA, page 16.

	This is the base-class for generated symbol types,
	with definitions for interesting magic-methods.
	It's somewhere between a dataclass and a namedtuple.
	"""
	_arity_: int
	__slots__: tuple
	_type_predicates_: tuple
	_appearance_: str
	def __setattr__(self, key, value): raise TypeError
	def __delattr__(self, item): raise TypeError
	def __init__(self, *args):
		if __debug__ and len(args) != self._arity_:
			raise TypeError(self._appearance_+" got %d arguments"%len(args))
		for f,v,check in zip(self.__slots__, args, self._type_predicates_):
			if __debug__ and not check(v):
				raise TypeError("%s: Field %r failed well-formed-ness check with value %r"%(self._appearance_,f,v))
			object.__setattr__(self, f,v)
	def __str__(self): return self._appearance_
	def __iter__(self):
		return (getattr(self, s) for s in self.__slots__)


class TreePass(abc.ABC):
	"""
	Compiler passes are callable:
	They implement a simple form of double-dispatch by calling a method named
	for the type of the first argument, and with the term again as first argument.
	All remaining arguments are passed through unexamined.
	This provides an easy way to write micro-passes,
	but it means the per-symbol methods must have explicit recursive calls
	if you intend for processing to continue.
	
	(Incidentally, see also the function "post_order".)
	"""
	@abc.abstractmethod
	def _unhandled_(self, term, *args, **kwargs):
		""" Deal with unknown symbols here. """
		raise NotImplementedError(type(self))
	
	def __call__(self, term, *args, **kwargs):
		method = getattr(self, term.__class__.__name__, self._unhandled_)
		return method(term, *args, **kwargs)
	
	pass

class SparseWalk(TreePass):
	""" Calls your methods on interesting nodes; does not build a new tree. """
	def _unhandled_(self, term, *args, **kwargs):
		for child in term:
			self(child, *args, **kwargs)

class SparseRewrite(TreePass):
	def _unhandled_(self, term, *args, **kwargs):
		"""
		This is the generic structural-copy method.
		It conveniently also works for lists and tuples.
		It also goes out of its way to share identical sub-trees.
		Smart pruning would be a nice feature here.
		The very smartest pruning would take advantage of a bottom-up DFA generated from the translation plan,
		marking nodes upon creation with their eligibility for subsequent traversals. But that's a long way off.
		Also, this highlights the need for traceability.
		"""
		kids = tuple(term)
		xlat = tuple(self(child, *args, **kwargs) for child in kids)
		if all(a is b for a,b in zip(kids, xlat)):
			return term
		else:
			return type(term)(*xlat)

class StrictPass(TreePass):
	def _unhandled_(self, node, *args, **kwargs):
		""" Strict passes must implement something for every symbol. """
		appearance = str(node) if isinstance(node, BaseTerm) else str(type(node))
		raise RuntimeError("class %s neglects to handle symbol %s"%(type(self), appearance))


def post_order(visitor, *, otherwise=lambda x:x):
	"""
	Logic for a simple bottom-up left-to-right micro-pass:

	The visitor is assumed to have methods named for symbols.
	These are called in post-order with bottom-up results.

	If the algorithm encounters a term for which no method exists,
	it returns `otherwise(` that term `)` instead of delving further.
	The default `otherwise` is to return the node as-is.
	(Use otherwise=None to raise AttributeError instead.)
	Lists and tuples get a structural mapping.
	All other data types are returned as-is.
	"""
	def visit(term):
		if isinstance(term, BaseTerm):
			try: method = getattr(visitor, term.__class__.__name__)
			except AttributeError:
				if otherwise is None: raise
				else: return otherwise(term)
		elif isinstance(term, (list, tuple)):
			method = type(term)
		else:
			return term
		return method(*(visit(t) for t in term))
	return visit
