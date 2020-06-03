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

## Precedence
I believe if you're going to write a grammar for which non-determinism is a deliberate
and intentional characteristic, then the fact should be part of the defining document rather
than (for example) a command-line parameter you have to remember to use. For the moment,
and until someone shares a better idea, I'm considering it as sort of like a catch-all
precedence declaration.
```
%nondeterministic Palindrome
```
The design space for this is wide open. We'd like to avoid facilitating grammar bugs
caused by accidentally having a non-deterministic situation where it's not intended or
anticipated. To this end, you could, for instance:
* allow the author to specify a sub-set of look-ahead tokens expected at non-deterministic
situations.
* ask for a list of non-terminal symbols that have ambiguous parse trees not resolved by
other P&A declarations.

This system attempts to use the second of these methods.

## Productions: Palindrome HiddenRight HiddenLeft HiddenMid
Recall that the `_` (underscore) refers back to the head of a rule.

Palindromes are a canonical `not-LR(k) for any k` non-deterministic but unambiguous example:
```
Palindrome -> Core | a _ a | b _ b
Core -> E | a | b
```

There's a stress test for dealing well with epsilon rules:
Hidden Recursion causes weak algorithms to either miss
correct sentences or diverge. 

```
E -> :nothing
HiddenRight -> a _ E | b
HiddenLeft -> a | E _ b
HiddenMid -> a | E _ E 
```

Hidden left recursion causes the brute-force approach to
diverge because it cannot guess how many times it must
reduce an epsilon rule before shifting a token.

Hidden right recursion is fine under brute force because eventually
the parser runs out of branches to cancel, but it causes weaker GSS
implementations to reject some of the language. Unfortunately, for
the moment it appears strength costs time and complexity.

You could argue that hidden-middle recursion is pathological:
A corresponding parse tree has every depth at once. Nevertheless,
somehow the system magically copes with it. Actually, no magic at all:
It just happens to be a recursive pun. With care, these things
have a place in language processing.
