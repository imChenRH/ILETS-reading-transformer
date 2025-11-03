# PDF Title Analysis Report

## Query: PDFs with "matching" in title

**Result:** None of the 20 PDF files have "matching" in their passage titles.

## All PDF Titles (20 files)

| # | Filename | Extracted Title |
|---|----------|-----------------|
| 1 | 60. P3 - A closer examination... | A closer examination of a study on verbal and non-verbal messages |
| 2 | 61. P3 - Book Review... | Book Review: |
| 3 | 65. P3 - Does class size matter... | Does Class Size Matter? |
| 4 | 66. P3 - Elephant Communication... | Elephant Communication |
| 5 | 67. P3 - Flower Power... | Write the correct number, i–viii, in boxes 27–33 on your answer sheet. |
| 6 | 70. P3 - Insect-inspired robots... | Insect-inspired robots |
| 7 | 76. P3 - Living dunes... | Write the correct number, i–ix, in boxes 27 – 33 on your answer sheet. |
| 8 | 78. P3 - Music Language... | Music: Language We All Speak |
| 9 | 81. P3 - Robert Louis Stevenson... | Robert Louis Stevenson |
| 10 | 82. P3 - Some views on headphones... | Some views on the use of headphones |
| 11 | 84. P3 - The Analysis of Fear... | Match each response with the correct condition, A, B or C. |
| 12 | 89. P3 - The Fruit Book... | The Fruit Book |
| 13 | 91. P3 - Margaret Mahy... | READING PASSAGE 3 |
| 14 | 92. P3 - The Pirahã people... | The Pirahã people of Brazil |
| 15 | 101. P3 - Yawning... | Yawning |
| 16 | 111. P3 - Whale Culture... | Whale Culture |
| 17 | 123. P3 - Images and Places... | Write the correct number, i–viii, in boxes 27–32 on your answer sheet. |
| 18 | 127. P3 - Science and Filmmaking... | Science and Filmmaking |
| 19 | 130. P3 - Tasmania's Museum... | Tasmania's Museum of Old and New Art |
| 20 | 147. P3 - Movement Underwater... | Movement Underwater |

## Note on Title Extraction Issues

Some PDFs (marked above) have question instructions extracted as titles instead of the actual passage title:
- PDF #5, #7, #17: "Write the correct number..." (question instruction)
- PDF #11: "Match each response..." (question instruction)
- PDF #13: "READING PASSAGE 3" (section header)

These appear to be title extraction issues where the parser identified instruction text as the title. However, this doesn't affect question parsing functionality, as the questions are correctly identified regardless of the title extraction.

## Word "Matching" Usage

While no PDF titles contain "matching", the word does appear in:
- **Question types**: Many PDFs contain "matching" question types (Matching Headings, Matching Features, Matching Information, Matching Sentence Endings)
- **Question instructions**: Like in PDF #11 where "Match each response..." was incorrectly extracted as the title

## Summary

- **Total PDFs analyzed**: 20
- **PDFs with "matching" in title**: 0
- **PDFs with matching-type questions**: Multiple (but title doesn't contain the word)
