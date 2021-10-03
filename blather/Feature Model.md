# Feature Model for Grammars

In practice, we take a context-free grammar (CFG) and decorate it with a bunch of extra features.

## The CFG consists of:
* Terminal Symbols
* Non-terminal Symbols
* Production Rules, each consisting of:
  * Left-Hand Side (LHS) Symbol
  * Right-Hand Side (RHS) String-of-Symbols

In terms of theory, that's literally all there is to it.
In practice, we also like to have a few extra features.


## Operator-Precedence works by:
  * Assigning precedence and associativity to terminals.
    (Not every terminal symbol necessarily has an assignment.)
  * Providing a way to work out the symbol which controls the relative binding strength of a rule.
    (It's bound according to some token, which is usually drawn from the rule but may be specified separately.)
  * Optionally associating an explicitly-specified precedence-symbol to a rule.
  * Providing a conflict resolution operation for inadequacies of the context-free grammar.


## S-Attribution works by:
  * Rules are associated with actions to take on recognition of the rule.
  * Actions require an association between RHS symbols and some sort of message to the parse driver.
    (Some standard messages might be appropriate.)
  * This amounts to a bottom-up tree transduction.


## Mid-Rule Actions work by:
  * You can embed actions in the middle of rules, which translate to sort of like epsilon-gensyms with
    limited left-context visibility: They can "see" the symbols to their left in the parent rule.
  * This means rules need to be *de-sugared* after a fashion.


## General Left-Attribution *could* work by:
  * Maybe there's explicit leftward-visibility if and only if you can prove what's in the left context,
    which is not today's problem.
    * It has to do with path-lengths in the HFA, so it's feasible.
  * If the relevant path-lengths are not constant, then L-attribute stack-discipline may probably be
    achieved with special epsilon-gensyms (similar to mid-rule actions) managing an environment display.
    * This approach is more universal, but less efficient in certain cases.
  * In any event, there should be syntax to support and validate that inherited attributes are in scope.


## Grammar Macros work by:
  * Defining parametric rules associated with parametric symbols.
  * De-sugaring rules by:
    * Replacing call-sites (consistently) with *mangled* non-terminals, and
    * Defining said mangled symbols (once) with the proper substitutions made.
    * Dealing *very carefully* with macros-within-macros.
    * (This whole thing may be a workflow / transitive-closure problem.)

