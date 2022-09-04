# Binary Palindromes

The language of palindromes is a canonical example  language:
It is context-free and unambiguous, but *not-LR(k) for any k* no matter how you write the grammar.
Palindromes require a parser capable of dealing with nondeterminism.

## Precedence

If you plan to write a non-LR(1) grammar on purpose, the current way to note that in your specification is as follows:

```
%nondeterministic
```

## Productions: Palindrome 
(Recall that the `_` (underscore) refers back to the head of a rule.)

```
Palindrome -> epsilon | a | b | a _ a | b _ b
epsilon -> :nothing
```

