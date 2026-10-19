# Banned claims

The harness verifier loads every line of the form `- regex: ...` below. A report claim that
matches any pattern is rejected.

## Patterns
- regex: `\b(is|was|are|were)\s+caused\s+by\b`
- regex: `\bcaused\s+by\b`
- regex: `\b(caused|causing)\b`
- regex: `\bcauses\b(?!\s+(of|are|were|may|might|could|can|cannot|include|including|need|needs|is|worth|for|such|that|which|like|and|or)\b|\s*[,.;:?!)]|\s*$)`
- regex: `\b(led|leads)\s+to\b`
- regex: `\b(resulted|resulting)\s+(in|from)\b`
- regex: `\bresponsible\s+for\b`
- regex: `\b(due\s+to|because\s+of|owing\s+to|as\s+a\s+result\s+of)\b(?!\s+(the\s+|a\s+|an\s+)?((missing|incomplete|absent|unavailable|insufficient|unknown|unrecorded|no|lack\s+of)\s+(\w+\s+)?(records?|data|information|quantit(y|ies)|dates?|entr(y|ies)|values?|details?)|gaps?\s+in\s+(the\s+)?(\w+\s+)?records?)\b)`
- regex: `\bdefinitely\b`
- regex: `\bcertainly\b`
- regex: `\bdeficiency\s+of\b`
- regex: `\b(is|are|was|were|has|have)\s+(?!no\b|not\b)(an?\s+)?(\w+\s+)?deficien(cy|t)\b`
- regex: `\b(is|are|was|were|has|have)\s+(?!no\b|not\b)(an?\s+)?(\w+\s+)?(infections?|infected|blights?|rusts?|mildews?|virus(es)?|rots?|fung(us|i)|diseases?|diseased)\b`
- regex: `\b(infected|suffering)\s+(with|from)\b`
- regex: `\bthe\s+(cause|disease|problem)\s+is\b`
- regex: `\b(ye|yeh|yah)\s+bimari\s+hai\b`
- regex: `\bbimari\s+hai\b`
- regex: `\b(infection|blight|rust|mildew|virus|rot|fungus|disease)\s+(hai|hain)\b`
- regex: `\bki\s+wajah\s+se\s+(hai|hain|hua|hui|hue)\b`
- regex: `\b(pakka|yaqeenan|yakeenan)\b`
- regex: `\bki\s+kami\s+(hai|hui)\b`
- regex: `یہ بیماری ہے`
- regex: `بیماری ہے`
- regex: `(انفیکشن|وائرس|فنگس|پھپھوندی|بلائٹ) (ہے|ہیں)`
- regex: `کی وجہ سے (ہے|ہیں|ہوا|ہوئی|ہوئے)`
- regex: `یقین(اً|ًا|ا)`
- regex: `کی کمی (ہے|ہوئی)`

## Allowed rewrites
| Banned | Allowed |
|---|---|
| The yellowing is caused by urea. | The records show urea doubled 7 days before the yellowing (E-005); this may be worth investigating. |
| This is nitrogen deficiency. | Nutrient levels cannot be concluded from the records; a soil test may be worth asking about. |
| Ye bimari hai. | Records se bimari ka pata nahi chal sakta; expert se poochna behtar hai. |
| یہ بیماری ہے۔ | ریکارڈ سے بیماری کا پتا نہیں چل سکتا؛ ماہر سے پوچھنا بہتر ہے۔ |
| Urea caused the yellowing. | The records show urea doubled 7 days before the yellowing (E-005); whether the two are linked cannot be concluded from the records. |
| This is a fungal infection. | The records cannot show what the spots are; an agricultural expert may be worth consulting. |
| Spray a fungicide. | Ask an agricultural expert before any spray. |

The patterns cover diagnosis and cause-as-fact wording, including "caused", "led to",
"resulted in", "responsible for", "due to" and "because of". "Due to" and "because of" are
allowed only for a missing-records reason: "cannot be concluded due to missing records".
Treatment and dosage advice, like the last row, is never allowed either; the app's verifier
rejects it with a separate check.

For missing records in Roman Urdu or Urdu, write "record mojood nahi" or "ریکارڈ موجود نہیں".
The patterns above also reject "ki kami hai" and "کی کمی ہے", even for "records ki kami hai".
