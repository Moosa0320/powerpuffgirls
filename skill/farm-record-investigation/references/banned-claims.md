# Banned claims

The harness verifier loads every line of the form `- regex: ...` below. A report claim that
matches any pattern is rejected.

## Patterns
- regex: `\b(is|was|are|were)\s+caused\s+by\b`
- regex: `\bcaused\s+by\b`
- regex: `\bdefinitely\b`
- regex: `\bcertainly\b`
- regex: `\bdeficiency\s+of\b`
- regex: `\b(has|have|is|are)\s+(an?\s+)?(infection|blight|rust|mildew|virus|rot|fungus|disease)\b`
- regex: `\b(infected|suffering)\s+(with|from)\b`
- regex: `\bthe\s+(cause|disease|problem)\s+is\b`
- regex: `\b(ye|yeh|yah)\s+bimari\s+hai\b`
- regex: `\bbimari\s+hai\b`
- regex: `\bki\s+wajah\s+se\s+(hai|hua|hui)\b`
- regex: `\b(pakka|yaqeenan|yakeenan)\b`
- regex: `\bki\s+kami\s+(hai|hui)\b`
- regex: `یہ بیماری ہے`
- regex: `بیماری ہے`
- regex: `کی وجہ سے (ہے|ہوا|ہوئی)`
- regex: `یقیناً`
- regex: `کی کمی (ہے|ہوئی)`

## Allowed rewrites
| Banned | Allowed |
|---|---|
| The yellowing is caused by urea. | The records show urea doubled 7 days before the yellowing (E-005); this may be worth investigating. |
| This is nitrogen deficiency. | Nutrient levels cannot be concluded from the records; a soil test may be worth asking about. |
| Ye bimari hai. | Records se bimari ka pata nahi chal sakta; expert se poochna behtar hai. |
| Spray a fungicide. | Ask an agricultural expert before any spray. |