---
name: farm-record-investigation
description: Investigates a crop problem using a farmer's recorded field events. Builds a chronological timeline, separates recorded facts from possible explanations, detects missing records, and prepares evidence-cited reports and questions for an agricultural expert. Use when a user asks what happened in a field before a symptom appeared. Never diagnoses.
license: Apache-2.0
metadata:
  version: 1.0.0
---

# Farm Record Investigation

## When to use
The user asks what changed in a field before a crop symptom, wants a timeline of farm events, or wants to prepare for an agricultural expert visit.

## Procedure
1. Identify the field and the symptom date. If the symptom date is unknown, ask for it.
2. Run scripts/timeline.py for the window (default 14 days before the symptom).
3. Run scripts/gaps.py to find missing records.
4. Run scripts/compare.py for numeric changes (dose, water, rainfall).
5. Read references/banned-claims.md, then write the report in three sections: What the records show, What may be worth investigating, Questions to ask next.
6. Cite event IDs for every statement of fact.
7. List missing records and what cannot be concluded because of them.

Read references/investigation-method.md when choosing a window or handling approximate dates, and references/question-bank.md when writing questions for the expert.

## Rules
- Never state a cause as fact. Say "may be worth investigating".
- Never recommend a specific pesticide, fungicide or dosage.
- Separate farmer-reported facts, photo observations and AI observations.
- Recommend an agricultural expert when symptoms spread or persist.

## Output format
See assets/report-template.md.