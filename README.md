# What is this?

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

Full documentation is moving from [the wiki page](https://github.com/kjosib/booze-tools/wiki)
over to [ReadTheDocs](https://boozetools.readthedocs.io/en/latest/).
Worked examples may be found at [/example/](https://github.com/kjosib/booze-tools/tree/master/example/).

# Priorities?
* These operate within a Python environment.
* They have some features not found in other such tools.
* The code is deliberately kept simple, small and well-factored:
    * Easy to extend, approachable, and informative. 
    * Aiming for suitability in an instructional context.
* These modules do not generate free-standing code:
    * Mini-Foo plugs directly into a Python application and works right away, which is nice for rapid prototyping.
    * MacroParse compiles automatons to JSON, and appropriate run-time support is in the library.
    * Code generation for other languages is foreseeable: translate the JSON and supply a suitable runtime.
* Performance is accordingly NOT a top priority, but:
    * the profiler has been used to solve one or two problems,
    * if someone wants to play with the profiler they are welcome, and
    * contributions in that vein will be accepted as long as they are consistent with the higher priorities.

# What Else?
There are several complete worked example scanners and parsers in the `example` folder. Start with the JSON ones: they have the best introductory commentary to walk you through getting started.

There are unit tests. They're not vast and imposing, but they exercise the interface both directly and via the example code.

There is a wiki linked above. It has background and more detail about what this is and how to use it.

# Oh by the way..
I'm NOT a [crack-pot](https://github.com/kjosib/booze-tools/blob/master/docs/P%20vs%20NP.md). Really I'm not.
