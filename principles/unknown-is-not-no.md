## unknown-is-not-no

**Rule:** Missing information goes to questions, never to rejection.

If the posting doesn't say, or the profile answer is `unsure`, the result is a question for the candidate or the recruiter. Only an explicit, quoted restriction that conflicts with an explicit profile answer can block.

_Enforced by:_ `agents/fit.py:restriction_effect` computes blocking in code from `profile.authorization`.
