# Results summary

Cells: percent [95% Wilson CI] (k/n). Utility = benign run (attack none) with the same suite/model/defense/task language.

## Attack conditions

| suite | provider | model | defense | task lang | payload lang | Utility | Utility under attack | ASR | errors |
|---|---|---|---|---|---|---|---|---|---|
| banking | gemini | gemini-3.5-flash-lite | none | en | en | 93.8 [71.7, 98.9] (15/16) | 66.7 [55.2, 76.5] (48/72) | 0.0 [0.0, 5.1] (0/72) | 0 |
| banking | gemini | gemini-3.5-flash-lite | none | en | hi | 93.8 [71.7, 98.9] (15/16) | 63.9 [52.4, 74.0] (46/72) | 0.0 [0.0, 5.1] (0/72) | 0 |
| banking | gemini | gemini-3.5-flash-lite | none | en | hi_latn | 93.8 [71.7, 98.9] (15/16) | 66.7 [55.2, 76.5] (48/72) | 0.0 [0.0, 5.1] (0/72) | 0 |
| banking | gemini | gemma-4-26b-a4b-it | none | en | en | 93.8 [71.7, 98.9] (15/16) | 74.6 [63.4, 83.3] (53/71) | 38.0 [27.6, 49.7] (27/71) | 2 |
| banking | gemini | gemma-4-26b-a4b-it | none | en | hi | 93.8 [71.7, 98.9] (15/16) | 81.9 [71.5, 89.1] (59/72) | 11.1 [5.7, 20.4] (8/72) | 0 |
| banking | gemini | gemma-4-26b-a4b-it | none | en | hi_latn | 93.8 [71.7, 98.9] (15/16) | 81.9 [71.5, 89.1] (59/72) | 4.2 [1.4, 11.5] (3/72) | 0 |

## Benign utility (no attack)

| suite | provider | model | defense | task lang | Utility | Utility (state-only checks) | Utility (digit-normalized) | errors |
|---|---|---|---|---|---|---|---|---|
| banking | gemini | gemini-3.5-flash-lite | none | en | 93.8 [71.7, 98.9] (15/16) | 92.9 [68.5, 98.7] (13/14) | 93.8 [71.7, 98.9] (15/16) | 0 |
| banking | gemini | gemini-3.5-flash-lite | none | hi | 87.5 [64.0, 96.5] (14/16) | 85.7 [60.1, 96.0] (12/14) | 87.5 [64.0, 96.5] (14/16) | 0 |
| banking | gemini | gemini-3.5-flash-lite | none | hi_latn | 93.8 [71.7, 98.9] (15/16) | 92.9 [68.5, 98.7] (13/14) | 93.8 [71.7, 98.9] (15/16) | 0 |
| banking | gemini | gemma-4-26b-a4b-it | none | en | 93.8 [71.7, 98.9] (15/16) | 92.9 [68.5, 98.7] (13/14) | 93.8 [71.7, 98.9] (15/16) | 0 |
| banking | gemini | gemma-4-26b-a4b-it | none | hi | 93.8 [71.7, 98.9] (15/16) | 92.9 [68.5, 98.7] (13/14) | 93.8 [71.7, 98.9] (15/16) | 0 |
| banking | gemini | gemma-4-26b-a4b-it | none | hi_latn | 87.5 [64.0, 96.5] (14/16) | 85.7 [60.1, 96.0] (12/14) | 87.5 [64.0, 96.5] (14/16) | 0 |
