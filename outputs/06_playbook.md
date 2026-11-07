# Leader playbook, planning week Feb 12-18 (one page)

Every number below comes from the fitted service curve and the recommended plan (`outputs/06_*.csv`). 'Tolerance' = callouts a block can absorb before P(meet target) drops below 80%. Base plan heads already include the expected-callout buffer.

## 1. Daily rules by warehouse (BASE plan)

| Warehouse | Dept | Shift | Days | Plan heads | Expected callouts | Tolerance (80% / 50%) | Flex you can pull | OT room | Action |
|---|---|---|---|---|---|---|---|---|---|
| 1 | FE | EVE | weekday | 16 | 0.9 | 2 / 2 | 0 | 3 | then OT up to 3 head(s) (+$37/head); beyond that: accept risk, see escalation table |
| 1 | FE | MID | weekday | 17 | 1.1 | 2 / 3 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 1 | FE | OPEN | weekday | 10 | 0.6 | 1 / 2 | 0 | 2 | then OT up to 2 head(s) (+$37/head); beyond that: accept risk, see escalation table |
| 1 | FE | EVE | weekend | 24 | 1.6 | 2 / 4 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 1 | FE | MID | weekend | 35 | 2.3 | 1 / 3 | 1 | 0 | pull up to 1 cross-trained from Merch (partner stays >= 90%); OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 1 | FE | OPEN | weekend | 26 | 1.7 | 4 / 5 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 1 | Merch | EVE | weekday | 11 | 0.4 | 2 / 2 | 0 | 1 | then OT up to 1 head(s) (+$58/head); beyond that: accept risk, see escalation table |
| 1 | Merch | MID | weekday | 11 | 0.4 | 1 / 2 | 1 | 1 | pull up to 1 cross-trained from FE (partner stays >= 90%); then OT up to 1 head(s) (+$48/head); beyond that: accept risk, see escalation table |
| 1 | Merch | OPEN | weekday | 16 | 0.6 | 1 / 2 | 0 | 1 | then OT up to 1 head(s) (+$58/head); beyond that: accept risk, see escalation table |
| 1 | Merch | EVE | weekend | 11 | 0.6 | 1 / 1 | 1 | 0 | pull up to 1 cross-trained from FE (partner stays >= 90%); OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 1 | Merch | MID | weekend | 17 | 0.9 | 2 / 3 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 1 | Merch | OPEN | weekend | 19 | 1.1 | 1 / 2 | 2 | 0 | pull up to 2 cross-trained from FE (partner stays >= 90%); OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 1 | Pharm | EVE | weekday | 4 | 0.2 | 1 / 1 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 1 | Pharm | MID | weekday | 4 | 0.2 | 1 / 1 | 0 | 1 | then OT up to 1 head(s) (+$48/head); beyond that: accept risk, see escalation table |
| 1 | Pharm | OPEN | weekday | 4 | 0.2 | 1 / 1 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 1 | Pharm | MID | weekend | 2 | 0.1 | 1 / 1 | 0 | 1 | then OT up to 1 head(s) (+$80/head); beyond that: accept risk, see escalation table |
| 1 | Pharm | OPEN | weekend | 3 | 0.2 | 1 / 1 | 0 | 1 | then OT up to 1 head(s) (+$64/head); beyond that: accept risk, see escalation table |
| 2 | FE | EVE | weekday | 20 | 1.2 | 2 / 3 | 0 | 3 | then OT up to 3 head(s) (+$38/head); beyond that: accept risk, see escalation table |
| 2 | FE | MID | weekday | 21 | 1.3 | 2 / 3 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 2 | FE | OPEN | weekday | 12 | 0.7 | 2 / 2 | 1 | 4 | pull up to 1 cross-trained from Merch (partner stays >= 90%); then OT up to 4 head(s) (+$38/head); beyond that: accept risk, see escalation table |
| 2 | FE | EVE | weekend | 29 | 1.9 | 2 / 4 | 1 | 0 | pull up to 1 cross-trained from Merch (partner stays >= 90%); OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 2 | FE | MID | weekend | 45 | 2.9 | 3 / 6 | 1 | 0 | pull up to 1 cross-trained from Merch (partner stays >= 90%); OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 2 | FE | OPEN | weekend | 31 | 2.0 | 3 / 5 | 1 | 0 | pull up to 1 cross-trained from Merch (partner stays >= 90%); OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 2 | Merch | EVE | weekday | 13 | 0.5 | 1 / 2 | 1 | 4 | pull up to 1 cross-trained from FE (partner stays >= 90%); then OT up to 4 head(s) (+$60/head); beyond that: accept risk, see escalation table |
| 2 | Merch | MID | weekday | 13 | 0.5 | 1 / 2 | 0 | 4 | then OT up to 4 head(s) (+$50/head); beyond that: accept risk, see escalation table |
| 2 | Merch | OPEN | weekday | 20 | 0.7 | 2 / 3 | 0 | 2 | then OT up to 2 head(s) (+$60/head); beyond that: accept risk, see escalation table |
| 2 | Merch | EVE | weekend | 15 | 0.8 | 3 / 4 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 2 | Merch | MID | weekend | 19 | 1.1 | 2 / 3 | 1 | 0 | pull up to 1 cross-trained from FE (partner stays >= 90%); OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 2 | Merch | OPEN | weekend | 25 | 1.4 | 2 / 4 | 2 | 0 | pull up to 2 cross-trained from FE (partner stays >= 90%); OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 2 | Pharm | EVE | weekday | 4 | 0.2 | 1 / 1 | 0 | 1 | then OT up to 1 head(s) (+$58/head); beyond that: accept risk, see escalation table |
| 2 | Pharm | MID | weekday | 4 | 0.2 | 1 / 1 | 0 | 1 | then OT up to 1 head(s) (+$50/head); beyond that: accept risk, see escalation table |
| 2 | Pharm | OPEN | weekday | 5 | 0.2 | 1 / 1 | 0 | 1 | then OT up to 1 head(s) (+$58/head); beyond that: accept risk, see escalation table |
| 2 | Pharm | MID | weekend | 2 | 0.2 | 1 / 1 | 0 | 1 | then OT up to 1 head(s) (+$83/head); beyond that: accept risk, see escalation table |
| 2 | Pharm | OPEN | weekend | 3 | 0.2 | 1 / 1 | 0 | 1 | then OT up to 1 head(s) (+$67/head); beyond that: accept risk, see escalation table |
| 4 | FE | EVE | weekday | 21 | 1.2 | 2 / 3 | 0 | 3 | then OT up to 3 head(s) (+$38/head); beyond that: accept risk, see escalation table |
| 4 | FE | MID | weekday | 22 | 1.3 | 2 / 3 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 4 | FE | OPEN | weekday | 12 | 0.7 | 1 / 2 | 0 | 4 | then OT up to 4 head(s) (+$38/head); beyond that: accept risk, see escalation table |
| 4 | FE | EVE | weekend | 31 | 2.0 | 3 / 5 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 4 | FE | MID | weekend | 48 | 3.1 | 4 / 7 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 4 | FE | OPEN | weekend | 32 | 2.1 | 3 / 5 | 1 | 1 | pull up to 1 cross-trained from Merch (partner stays >= 90%); then OT up to 1 head(s) (+$38/head); beyond that: accept risk, see escalation table |
| 4 | Merch | EVE | weekday | 13 | 0.5 | 1 / 2 | 1 | 3 | pull up to 1 cross-trained from FE (partner stays >= 90%); then OT up to 3 head(s) (+$59/head); beyond that: accept risk, see escalation table |
| 4 | Merch | MID | weekday | 13 | 0.5 | 1 / 2 | 1 | 4 | pull up to 1 cross-trained from FE (partner stays >= 90%); then OT up to 4 head(s) (+$49/head); beyond that: accept risk, see escalation table |
| 4 | Merch | OPEN | weekday | 19 | 0.7 | 2 / 2 | 0 | 2 | then OT up to 2 head(s) (+$59/head); beyond that: accept risk, see escalation table |
| 4 | Merch | EVE | weekend | 13 | 0.7 | 1 / 2 | 2 | 0 | pull up to 2 cross-trained from FE (partner stays >= 90%); OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 4 | Merch | MID | weekend | 18 | 1.0 | 2 / 3 | 2 | 0 | pull up to 2 cross-trained from FE (partner stays >= 90%); OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 4 | Merch | OPEN | weekend | 24 | 1.3 | 2 / 3 | 2 | 2 | pull up to 2 cross-trained from FE (partner stays >= 90%); then OT up to 2 head(s) (+$51/head); beyond that: accept risk, see escalation table |
| 4 | Pharm | EVE | weekday | 5 | 0.2 | 1 / 1 | 0 | 1 | then OT up to 1 head(s) (+$57/head); beyond that: accept risk, see escalation table |
| 4 | Pharm | MID | weekday | 5 | 0.2 | 1 / 1 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |
| 4 | Pharm | OPEN | weekday | 5 | 0.2 | 1 / 1 | 0 | 1 | then OT up to 1 head(s) (+$57/head); beyond that: accept risk, see escalation table |
| 4 | Pharm | MID | weekend | 2 | 0.2 | 1 / 1 | 0 | 1 | then OT up to 1 head(s) (+$82/head); beyond that: accept risk, see escalation table |
| 4 | Pharm | OPEN | weekend | 3 | 0.2 | 1 / 1 | 0 | 0 | OT already fully used in the plan: no backfill room; beyond that: accept risk, see escalation table |

How to read a row: if callouts in that block exceed the 80% tolerance before the shift starts, act in the order shown. A tolerance of 0 means the block is already at its planning limit (usually all OT used): the first callout needs an action.

## 2. Scenario switches

**Storm advisory upgraded or promotion confirmed (switch to the PEAK plan).** Heads to add vs BASE, by warehouse and day:

| Warehouse | Date | Dept | BASE heads | PEAK heads | Add |
|---|---|---|---|---|---|
| 1 | 2026-02-13 | FE | 65 | 69 | +4 |
| 1 | 2026-02-13 | Merch | 41 | 50 | +9 |
| 1 | 2026-02-13 | Pharm | 11 | 12 | +1 |
| 1 | 2026-02-15 | FE | 83 | 87 | +4 |
| 1 | 2026-02-15 | Merch | 46 | 50 | +4 |
| 2 | 2026-02-13 | FE | 81 | 86 | +5 |
| 2 | 2026-02-13 | Merch | 49 | 59 | +10 |
| 2 | 2026-02-13 | Pharm | 12 | 13 | +1 |
| 2 | 2026-02-14 | Pharm | 5 | 6 | +1 |
| 2 | 2026-02-15 | FE | 101 | 106 | +5 |
| 2 | 2026-02-15 | Merch | 59 | 60 | +1 |
| 4 | 2026-02-13 | FE | 83 | 87 | +4 |
| 4 | 2026-02-13 | Merch | 49 | 64 | +15 |
| 4 | 2026-02-13 | Pharm | 13 | 14 | +1 |
| 4 | 2026-02-14 | FE | 119 | 120 | +1 |
| 4 | 2026-02-14 | Merch | 57 | 59 | +2 |
| 4 | 2026-02-14 | Pharm | 5 | 6 | +1 |
| 4 | 2026-02-15 | FE | 105 | 112 | +7 |
| 4 | 2026-02-15 | Merch | 55 | 58 | +3 |

Pre-stock on Thursday Feb 12 EVE: Merch Thursday evening blocks run at utilization W1 0.72 (10 heads, OT room 3), W2 0.74 (12 heads, OT room 4), W4 0.78 (11 heads, OT room 3). Each extra head there carries about 5 Merch workload units at the standard (6 h x 0.83 units/h), which is what one Friday OPEN head would otherwise carry. Moving receiving work to Thursday evening is the cheapest lever because Thursday OT room is unused and Friday/Saturday OPEN blocks are at capacity in PEAK.

**Illness cluster or crew shortage reported (switch to the DISRUPT plan).** Blocks that change vs BASE:

| Warehouse | Date | Shift | Dept | BASE | DISRUPT | Change | P(meet) in DISRUPT |
|---|---|---|---|---|---|---|---|
| 2 | 2026-02-13 | EVE | FE | 29 | 22 | -7 | 0.01 |
| 2 | 2026-02-13 | EVE | Merch | 14 | 13 | -1 | 0.73 |
| 2 | 2026-02-13 | MID | FE | 35 | 22 | -13 | 0.00 |
| 2 | 2026-02-13 | MID | Merch | 14 | 20 | +6 | 1.00 |
| 2 | 2026-02-13 | OPEN | FE | 17 | 15 | -2 | 0.39 |
| 2 | 2026-02-13 | OPEN | Merch | 21 | 20 | -1 | 0.88 |
| 2 | 2026-02-14 | EVE | FE | 32 | 16 | -16 | 0.00 |
| 2 | 2026-02-14 | EVE | Merch | 16 | 17 | +1 | 0.99 |
| 2 | 2026-02-14 | MID | FE | 45 | 23 | -22 | 0.00 |
| 2 | 2026-02-14 | MID | Merch | 19 | 21 | +2 | 0.99 |
| 2 | 2026-02-14 | OPEN | FE | 34 | 17 | -17 | 0.00 |
| 2 | 2026-02-14 | OPEN | Merch | 25 | 26 | +1 | 0.91 |
| 2 | 2026-02-15 | EVE | FE | 27 | 13 | -14 | 0.00 |
| 2 | 2026-02-15 | EVE | Merch | 14 | 15 | +1 | 0.99 |
| 2 | 2026-02-15 | MID | FE | 45 | 33 | -12 | 0.00 |
| 2 | 2026-02-15 | MID | Merch | 19 | 20 | +1 | 0.95 |
| 2 | 2026-02-15 | OPEN | FE | 29 | 15 | -14 | 0.00 |
| 2 | 2026-02-15 | OPEN | Merch | 26 | 27 | +1 | 0.99 |
| 2 | 2026-02-16 | MID | FE | 21 | 19 | -2 | 0.43 |
| 2 | 2026-02-16 | MID | Merch | 16 | 18 | +2 | 1.00 |
| 2 | 2026-02-16 | OPEN | Pharm | 4 | 3 | -1 | 0.80 |
| 4 | 2026-02-13 | OPEN | FE | 18 | 21 | +3 | 1.00 |
| 4 | 2026-02-13 | OPEN | Merch | 20 | 19 | -1 | 0.68 |

**Pharmacy cannot flex.** Pharmacy has no cross-trained cover and min_staff 2. When a pharmacy team member is out, OT is the only lever: protect pharmacy first because one missing head on a 3-4 head block moves P(meet) from above 0.95 to below 0.5 (see `06_playbook_blocks.csv`, p_after_1_callout).

## 3. Escalation order and what each step costs

| Dept | 1. Reallocate within dept | 2. Cross-train | 3. Overtime (premium per head-shift) | 4. Accept risk (P(meet) lost per head short, median / bad case) |
|---|---|---|---|---|
| FE | move a head between shifts of the same day: $0 (same rate), limited by availability | pull a cross-trained partner head: $0 premium; partner loses the P(meet) shown in 06_playbook_blocks | $36 on top of $111 | 0.11 / 0.22 |
| Merch | move a head between shifts of the same day: $0 (same rate), limited by availability | pull a cross-trained partner head: $0 premium; partner loses the P(meet) shown in 06_playbook_blocks | $53 on top of $165 | 0.13 / 0.28 |
| Pharm | move a head between shifts of the same day: $0 (same rate), limited by availability | not available (licensure) | $58 on top of $181 | 0.57 / 0.93 |

Rule of thumb from the curve: a head short on a block at the 90% line costs 0.1-0.4 of a block's P(meet); a head of OT costs $35-70 of premium. At $35-70 per head against a 10-40 point drop in P(meet), OT is almost always worth it on a block at its planning limit, and never worth it on a block with slack (tolerance >= 2).

## 4. Blocks to watch (recommended plan, P(meet) after callouts below 80%)

| Scenario | Warehouse | Date | Shift | Dept | Heads | Capacity | P(meet) submitted | P(meet) after callouts | Why |
|---|---|---|---|---|---|---|---|---|---|
| BASE | 1 | 2026-02-14 | MID | FE | 34 | 35 | 0.83 | 0.54 | all OT used, no backfill room |
| BASE | 1 | 2026-02-14 | EVE | Merch | 11 | 13 | 0.89 | 0.60 | all OT used, no backfill room |
| BASE | 1 | 2026-02-17 | OPEN | Pharm | 4 | 4 | 1.00 | 0.64 | all OT used, no backfill room |
| BASE | 2 | 2026-02-14 | EVE | FE | 32 | 33 | 0.95 | 0.71 | all OT used, no backfill room |
| BASE | 1 | 2026-02-14 | OPEN | Merch | 20 | 22 | 0.96 | 0.71 | all OT used, no backfill room |
| BASE | 2 | 2026-02-14 | MID | FE | 45 | 46 | 0.97 | 0.77 | all OT used, no backfill room |
| BASE | 1 | 2026-02-15 | OPEN | Merch | 19 | 21 | 0.97 | 0.77 | all OT used, no backfill room |
| BASE | 4 | 2026-02-14 | EVE | Merch | 14 | 16 | 0.97 | 0.78 | all OT used, no backfill room |
| BASE | 4 | 2026-02-14 | OPEN | Pharm | 3 | 3 | 0.96 | 0.80 | all OT used, no backfill room |
| DISRUPT | 2 | 2026-02-14 | OPEN | FE | 17 | 23 | 0.00 | 0.00 | capacity-bound |
| DISRUPT | 2 | 2026-02-14 | MID | FE | 23 | 30 | 0.00 | 0.00 | capacity-bound |
| DISRUPT | 2 | 2026-02-14 | EVE | FE | 16 | 21 | 0.00 | 0.00 | capacity-bound |
| DISRUPT | 2 | 2026-02-15 | OPEN | FE | 15 | 21 | 0.00 | 0.00 | capacity-bound |
| DISRUPT | 2 | 2026-02-15 | EVE | FE | 13 | 18 | 0.00 | 0.00 | capacity-bound |
| DISRUPT | 2 | 2026-02-13 | MID | FE | 22 | 23 | 0.00 | 0.00 | demand exceeds capacity even with all OT |
| DISRUPT | 2 | 2026-02-15 | MID | FE | 33 | 34 | 0.00 | 0.00 | demand exceeds capacity even with all OT |
| DISRUPT | 2 | 2026-02-13 | EVE | FE | 22 | 22 | 0.03 | 0.01 | demand exceeds capacity even with all OT |
| DISRUPT | 2 | 2026-02-13 | OPEN | FE | 15 | 15 | 0.63 | 0.39 | all OT used, no backfill room |
| DISRUPT | 2 | 2026-02-16 | MID | FE | 19 | 20 | 0.71 | 0.43 | all OT used, no backfill room |
| DISRUPT | 1 | 2026-02-14 | MID | FE | 34 | 35 | 0.83 | 0.54 | all OT used, no backfill room |
| DISRUPT | 1 | 2026-02-14 | EVE | Merch | 11 | 13 | 0.89 | 0.60 | all OT used, no backfill room |
| DISRUPT | 1 | 2026-02-17 | OPEN | Pharm | 4 | 4 | 1.00 | 0.64 | all OT used, no backfill room |
| DISRUPT | 4 | 2026-02-13 | OPEN | Merch | 19 | 20 | 0.82 | 0.68 | all OT used, no backfill room |
| DISRUPT | 1 | 2026-02-14 | OPEN | Merch | 20 | 22 | 0.96 | 0.71 | all OT used, no backfill room |
| DISRUPT | 2 | 2026-02-13 | EVE | Merch | 13 | 19 | 0.82 | 0.73 | capacity-bound |
| DISRUPT | 1 | 2026-02-15 | OPEN | Merch | 19 | 21 | 0.97 | 0.77 | all OT used, no backfill room |
| DISRUPT | 4 | 2026-02-14 | EVE | Merch | 14 | 16 | 0.97 | 0.78 | all OT used, no backfill room |
| DISRUPT | 4 | 2026-02-14 | OPEN | Pharm | 3 | 3 | 0.96 | 0.80 | all OT used, no backfill room |
| PEAK | 4 | 2026-02-13 | MID | FE | 34 | 35 | 0.03 | 0.01 | demand exceeds capacity even with all OT |
| PEAK | 1 | 2026-02-14 | OPEN | Merch | 20 | 22 | 0.03 | 0.01 | all OT used, no backfill room |
| PEAK | 1 | 2026-02-14 | MID | FE | 34 | 35 | 0.03 | 0.01 | demand exceeds capacity even with all OT |
| PEAK | 2 | 2026-02-14 | OPEN | Merch | 25 | 27 | 0.04 | 0.02 | all OT used, no backfill room |
| PEAK | 2 | 2026-02-14 | MID | FE | 45 | 46 | 0.24 | 0.06 | demand exceeds capacity even with all OT |
| PEAK | 2 | 2026-02-14 | EVE | FE | 32 | 33 | 0.26 | 0.09 | demand exceeds capacity even with all OT |
| PEAK | 4 | 2026-02-14 | OPEN | Merch | 27 | 29 | 0.26 | 0.11 | all OT used, no backfill room |
| PEAK | 4 | 2026-02-14 | EVE | FE | 35 | 36 | 0.27 | 0.12 | demand exceeds capacity even with all OT |
| PEAK | 4 | 2026-02-14 | MID | FE | 50 | 51 | 0.29 | 0.12 | demand exceeds capacity even with all OT |
| PEAK | 2 | 2026-02-13 | MID | FE | 35 | 35 | 0.30 | 0.16 | demand exceeds capacity even with all OT |
| PEAK | 4 | 2026-02-14 | MID | Merch | 18 | 22 | 0.30 | 0.16 | all OT used, no backfill room |
| PEAK | 1 | 2026-02-13 | MID | FE | 28 | 28 | 0.31 | 0.17 | demand exceeds capacity even with all OT |
| PEAK | 1 | 2026-02-14 | EVE | Merch | 11 | 13 | 0.35 | 0.20 | all OT used, no backfill room |
| PEAK | 4 | 2026-02-14 | EVE | Merch | 14 | 16 | 0.50 | 0.29 | all OT used, no backfill room |
| PEAK | 4 | 2026-02-13 | EVE | FE | 32 | 33 | 0.59 | 0.29 | all OT used, no backfill room |
| PEAK | 1 | 2026-02-14 | EVE | FE | 28 | 28 | 0.73 | 0.41 | all OT used, no backfill room |
| PEAK | 4 | 2026-02-14 | OPEN | FE | 35 | 37 | 0.74 | 0.46 | all OT used, no backfill room |
| PEAK | 2 | 2026-02-14 | MID | Merch | 19 | 22 | 0.74 | 0.51 | all OT used, no backfill room |
| PEAK | 1 | 2026-02-15 | OPEN | Merch | 19 | 21 | 0.79 | 0.54 | all OT used, no backfill room |
| PEAK | 4 | 2026-02-14 | OPEN | Pharm | 3 | 3 | 0.77 | 0.64 | all OT used, no backfill room |
| PEAK | 1 | 2026-02-17 | OPEN | Pharm | 4 | 4 | 1.00 | 0.64 | all OT used, no backfill room |
| PEAK | 1 | 2026-02-14 | OPEN | FE | 27 | 28 | 0.94 | 0.65 | all OT used, no backfill room |
| PEAK | 2 | 2026-02-13 | EVE | FE | 32 | 33 | 0.88 | 0.66 | all OT used, no backfill room |
| PEAK | 2 | 2026-02-15 | OPEN | FE | 29 | 31 | 0.94 | 0.67 | all OT used, no backfill room |
| PEAK | 2 | 2026-02-14 | OPEN | FE | 34 | 36 | 0.93 | 0.67 | all OT used, no backfill room |
| PEAK | 1 | 2026-02-13 | MID | Merch | 12 | 18 | 0.80 | 0.71 | capacity-bound |
| PEAK | 2 | 2026-02-15 | EVE | FE | 27 | 28 | 0.95 | 0.72 | all OT used, no backfill room |
| PEAK | 1 | 2026-02-13 | EVE | FE | 26 | 27 | 0.95 | 0.74 | all OT used, no backfill room |
| PEAK | 4 | 2026-02-15 | MID | FE | 49 | 50 | 0.97 | 0.76 | all OT used, no backfill room |
| PEAK | 4 | 2026-02-15 | EVE | Merch | 13 | 15 | 0.97 | 0.77 | all OT used, no backfill room |
| PEAK | 1 | 2026-02-15 | MID | FE | 38 | 39 | 0.97 | 0.79 | all OT used, no backfill room |