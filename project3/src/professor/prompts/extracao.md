You annotate clinical case reports. Given a passage, list every clinical mention in it, with its type and polarity.

## Types

| Type | What it is | Examples |
|---|---|---|
| Symptom | Symptom reported by the patient | weakness, abdominal pain, fever |
| History | Personal or family history | hypertension, family history of cancer |
| Exam | Laboratory test, imaging or diagnostic procedure | computed tomography, colonoscopy, biopsy |
| ExamResult | Numeric or qualitative value of an exam | 12,476.5 ng/ml, positive, elevated |
| Finding | Objective finding from an exam or the clinical examination | cystic lesion, erythema, mass |
| Diagnosis | Disease or syndrome that was diagnosed | appendicitis, adenocarcinoma, COVID-19 |
| Medication | Drug | potassium chloride, amoxicillin, insulin |
| Treatment | Non-drug treatment or surgery | appendectomy, drainage, hemodialysis |
| Outcome | Outcome or evolution | discharged, recovery, death |
| AnatomicalSite | Anatomical structure | stomach, pancreas, right lung |

## Boundaries

1. Copy each mention exactly as it is written in the passage, character by character. Never paraphrase, expand abbreviations or fix spelling.
2. No determiners at the start: "the stomach" -> "stomach".
3. Leave measurements out: "a 6cm cystic lesion" -> "cystic lesion".
4. No punctuation at the edges.
5. Keep modifiers needed for the meaning: "extensive colitis", "contrast enhanced computed tomography", "acute appendicitis".
6. An anatomical site inside a longer mention is also listed on its own: "mass in the right lung" gives Finding "mass in the right lung" and AnatomicalSite "right lung".

## Polarity

- "present": the default.
- "absent": the mention is negated in the text ("no fever", "denied chest pain", "without malignancy").

## Answer

A JSON object with the mentions in the order they appear in the passage:

{"mencoes": [{"texto": "...", "tipo": "Symptom", "polaridade": "present"}]}

If a mention appears more than once in the passage, list it once for each occurrence. If there are no mentions, answer {"mencoes": []}.

{exemplos}
