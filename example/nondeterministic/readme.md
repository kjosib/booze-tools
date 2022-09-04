# Non-Deterministic Grammars

There's not a whole lot of easily-found example grammars out there for interesting languages
with uncomfortable properties. Despite days and weeks of searching, I've found exactly three
main examples of non-deterministic context-free grammars with nontrivial semantics:

1. The language of palindromes, which is context-free, unambiguous, non-`LR(k)` for any `k`, and
trivially recognized without fancy parsing infrastructure.
2. Approximations of natural-language sentence structure, for which ambiguous parses are the
norm, not the exception. 
3. C++, which arguably should not be parsed (but I digress), and certain extended-Pascal
type-declarations.

I suspect this an open area for survey. If you have a nontrivial use for GLR methods
outside of the above three categories, then by all means please forward a description to the
GitHub project. 

## Declaring Nondeterminism

I believe if you're going to write a grammar for which non-determinism is a deliberate
and intentional characteristic, then the fact should be part of the defining document rather
than (for example) a command-line parameter you have to remember to use. For the moment,
and until someone shares a better idea, I'm considering it as sort of like a catch-all
precedence declaration.


The design space for this is wide open. We'd like to avoid facilitating grammar bugs
caused by accidentally having a non-deterministic situation where it's not intended or
anticipated. To this end, you could, for instance:
* allow the author to specify a sub-set of look-ahead tokens expected at non-deterministic
situations.
* ask for a list of non-terminal symbols that have ambiguous parse trees not resolved by
other P&A declarations.

This system attempts to use neither of these methods. It just takes a `%nondeterministic`
flag in the `# Precedence` section -- which is a bit weird, but it'll do for now.
