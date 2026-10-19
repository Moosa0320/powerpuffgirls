#!/usr/bin/env bash
# Validates the Agent Skill structure with no extra tools. CI also runs the agentskills.io
# reference validator (skills-ref) on the same folder.
set -euo pipefail
SKILL_DIR="skill/farm-record-investigation"
SKILL_MD="$SKILL_DIR/SKILL.md"
[ -f "$SKILL_MD" ] || { echo "missing $SKILL_MD"; exit 1; }
head -n 1 "$SKILL_MD" | grep -qx -- "---" || { echo "SKILL.md must start with frontmatter"; exit 1; }
NAME=$(grep -m1 '^name:' "$SKILL_MD" | sed 's/^name:[[:space:]]*//')
DESC=$(grep -m1 '^description:' "$SKILL_MD" | sed 's/^description:[[:space:]]*//')
[ "$NAME" = "$(basename "$SKILL_DIR")" ] || { echo "name '$NAME' must equal folder name"; exit 1; }
echo "$NAME" | grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$' || { echo "name must be lowercase-hyphen"; exit 1; }
[ -n "$DESC" ] || { echo "description is empty"; exit 1; }
[ "${#DESC}" -le 1024 ] || { echo "description longer than 1024 chars"; exit 1; }
for f in references/event-schema.md references/investigation-method.md references/banned-claims.md \
         references/question-bank.md scripts/timeline.py scripts/gaps.py scripts/compare.py \
         assets/report-template.md examples/sample_farm.csv; do
  [ -f "$SKILL_DIR/$f" ] || { echo "missing $SKILL_DIR/$f"; exit 1; }
done
python "$SKILL_DIR/scripts/timeline.py" "$SKILL_DIR/examples/sample_farm.csv" > /dev/null
echo "skill validation ok"
