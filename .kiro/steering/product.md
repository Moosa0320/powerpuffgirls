# FasalNama product rules

- FasalNama is an evidence timeline tool for farm records. It never diagnoses a crop disease, never states a cause as fact, never recommends a pesticide, fungicide or dosage.
- Allowed wording: "the records show", "may be worth investigating", "cannot be concluded because records are missing".
- Every factual statement in a report cites event IDs (format E-014). Photo observations cite photo IDs (P-007) and are labelled unconfirmed until the farmer confirms.
- Parsers never guess. Unknown quantity, product or date is null, not invented.
- Relative dates ("parson", "pichle hafte") are returned by the model as days_ago; code computes the calendar date.
- Every report ends with: "This is an evidence summary built from records, not a diagnosis."
- Languages: Urdu script, Roman Urdu, English. UI supports RTL.
