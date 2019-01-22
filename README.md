# booze-tools
Booze Tools are (will be) the complete programming-language development workbench,
all written in pure Python 3.7 (for now).

## "Mini-" modules:
The "mini" modules -- `miniscan` and `miniparse` -- provide convenient linear-time lexical scanning and LALR(1)
parsing as direct bolt-on to Python using the decorator mechanism to specify the actions that go along with
your patterns or production rules.

They work by constructing the same tables as conventional "generator"
programs, but then proceed to use those tables directly in-process instead of writing them out to a
separate program file. This makes them excellent for rapid prototyping.

### miniscan
`miniscan` adds certain major features above the typical FLEX-like baseline:
* Rule priority levels. For example, `foo` at rank 1 preempts `[a-z]+` at (default) rank 0 for input `foobar`.
* Character class intersection (and thus, difference). For instance, `[A-Z&&^AEIOU]` specifies the upper-case consonants.
* Counted repetition. For example, `{hex}{4,8}` matches between a 16 and 32-bit hexidecimal numeral.

Each pattern is associated with a function-of-one-argument, which is the scanner state as of a
successful match. Whatever this function returns (except the `None` object) gets emitted from the scanner.
(`None` is assumed to mean "ignore this match".)

Out of the box, those scanner states support methods to:
* query the matched text with `.matched_text()`
* switch among conditions/start-states with `.enter(...)`, `.push(...)`, and `.pop()` operations, or
* give back any or all of the match using the `.less(...)` method.

You build and use a miniscanner by:
1. Create a `miniscan.Definition()` object.
2. Use the `.on(...)` method to specify your lexical analysis rules. It's written for use as a decorator,
but you can "decorate" a string or `None` to get some convenient default behavior.
3. Named sub-expressions are defined using `.let(name, regex)` and
they become available within regular expresions via `{curlybraces}`.
4. As a convenience, the `.condition(...)` method returns an object to simplify
specifying several rules together for particular scan condition(s). It also
happens to work as a context manager.
5. Finally, the `.scan(text=...)` method provides an iterable of successive tokens.

The `.install_rule` methods are for internal use: You should not need to use them directly,
but it may be instructive to see what calls them. If you want to look at the generated discrete
finite automaton, the `.get_dfa()` method will supply your needs.

The architecture is intended to be easy to extend, approachable, and informative. 

See the wiki (linked above) for a bit more information and some differences in default behavior vs. other tools.

### miniparse
This is your basic LALR(1) parser accepting BNF rules, with one key extra-fancy feature:
* You can have more than one "start" symbol within a single grammar, and select among them at parse time.

Usage is vaguely similar to the miniscanner: you construct a MiniParse object, declare rules, and call
`.parse(...)` on a stream of tokens, which should be pairs consisting of `(token_type, attribute)`.
No special support exists for location tracking, but you can certainly include that kind of information
in the attribute cell from the scanner.

The best way to see how to write a `miniparse` grammar is to look in the unit tests and also the
defininition of the "rex" object within the `miniscan` module: it defines a grammar for regular
expression patterns.

The wiki page (linked above) contains a bit more information and some differences in default behavior vs. other tools.
