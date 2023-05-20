# What is this?

Parser/Scanner generator and run-time, all in Python. Plus various other handy btis and bobs.

# Why is it cool?

* Literate form: Definitions are embedded in MarkDown documents as code blocks.
* Macros eliminate most of the tedium typical of a context-free grammar.
* Productions are separate from action code, so you can see both the trees *and* the forest.
* Grammar and Scanner in a single definition file.
* JSON for tables means *in principle* other-language run-times should be straightforward.
* Full LR(1) deterministic, and also generalized / non-deterministic modes supported.

# Getting Started:

## Install
```
D:\>  pip install booze-tools
```

## Learn
Look in the [examples](https://github.com/kjosib/booze-tools/tree/master/example/)
for documentation by example.

* Gentle Introduction with `json.md` and `macro_json.py`.
  These have the best introductory commentary to walk you through getting started.
* For a complete working example, check out `calculator.md` and `calculator.py`.
* Then check out the other examples as they interest you.

Full documentation is moving from [the wiki page](https://github.com/kjosib/booze-tools/wiki)
over to [ReadTheDocs](https://boozetools.readthedocs.io/en/latest/).
But it's been a very slow process.

## Run

Translate a definition; generate `.automaton` file:
```
D:\> py -m boozetools my_grammar.md
```
Get a full run-down of the command-line options:
```
D:\> py -m boozetools -h
```

# What's New?

* Certain files are re-organized for the 0.6.x series.
* The project moves back to alpha stage for the time being.
* The 

# What's Here?

For now there are four major components. Eventually there will be more. These are:

* MiniParse -- Provides Minimal-LR(1)* or LALR(1) or Canonical-LR(1) with
  operator-precedence grammar facilities (like Lemon, YACC, or Bison), error
  productions, and good-and-proper error recovery.
  
* MiniScan -- Provides a DFA-based backtracking scanner (like Flex or Lex) with a few extra goodies.

* MacroParse -- This is the crown jewel of the package right now. It:
    * provides for a separate document containing the definitions of both a scanner and parser.
    * supports error productions and error-recovery in the same manner as MiniParse.
    * uses markdown format to make [just such a document](https://github.com/kjosib/booze-tools/tree/master/example/json.md) into a [literate program](http://www.literateprogramming.com/). 
    * enables a single such definition to be used for different applications on different host languages.
    * supports a macro language for simplifying otherwise-redundant parser specifications.
    * provides a suitable runtime library so the [examples](https://github.com/kjosib/booze-tools/tree/master/example/)
        run and pass the [tests](https://github.com/kjosib/booze-tools/tree/master/tests/).
    * can prepare parse and scan tables ahead of time (serialized to JSON) or just-in-time according to your needs.
    * can generate [DOT graphs](https://github.com/kjosib/booze-tools/blob/master/example/json.png) from grammars.

* Support Library: generic bits and bobs that may also be useful in other contexts.
    * Strongly Connected Components
    * Transitive Closure
    * Visitor Pattern
    * Equivalence Classification
    * Hamming Distance
    * Breadth First Traversal
    * Various small array hacks

The "minimal-LR(1)" algorithm used here is -- I believe -- provably minimal, even while it
respects precedence and associativity declarations in the usual way. It is strongly inspired
by the IELR(1) algorithm, but it is NOT exactly that algorithm. As far as I can tell it is a
new contribution. As such, I would appreciate feedback respecting your results with it.


# Priorities?
* These operate within a Python environment.
* They have some features not found in other such tools.
* Performance is accordingly not the top priority, but:
    * the profiler has been used to solve one or two problems,
    * if someone wants to play with the profiler they are welcome, and
    * contributions in that vein will be accepted as long as they are consistent with the higher priorities.

# What Else?

There are unit tests. They're not vast and imposing, but they exercise the interface both directly and via the example code.

# Bibliography:

* https://dl.acm.org/doi/pdf/10.1145/1780.1802

I'll add links as I track them down.

# Oh by the way..
I'm NOT a [crack-pot](https://github.com/kjosib/booze-tools/blob/master/docs/P%20vs%20NP.md). Really I'm not.
