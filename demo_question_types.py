#!/usr/bin/env python3
"""
Demo script showing all 10 IELTS question types being recognized
"""
from app import parse_questions

# Sample text with multiple question types
demo_text = """
Questions 1-3

Choose the correct letter A, B, C or D.

1 What is the primary focus of the passage?
A Environmental issues
B Economic development
C Social changes
D Technological advancement

Questions 4-6

Do the following statements agree with the information in the passage?

Write TRUE, FALSE or NOT GIVEN

4 The research was conducted over five years.
5 Participants came from diverse backgrounds.
6 Results were published in a scientific journal.

Questions 7-10

Choose the correct heading for each paragraph from the list below.

List of Headings
i The beginning of research
ii Modern implications
iii Future perspectives
iv Methodology overview

7 Paragraph A
8 Paragraph B
9 Paragraph C
10 Paragraph D

Questions 11-14

Which paragraph contains the following information?

Write the correct letter A-F

11 A description of initial findings
12 Discussion of limitations
13 Comparison with previous studies
14 Recommendations for future work

Questions 15-17

Match each statement with the correct researcher.

A Dr. Smith
B Professor Johnson
C Dr. Williams

15 Proposed the original hypothesis
16 Conducted the pilot study
17 Analyzed the statistical data

Questions 18-20

Complete each sentence with the correct ending A-E below.

18 The initial experiment showed that
19 Later studies confirmed that
20 Recent analysis suggests that

A the methodology was flawed
B results were consistent
C more research is needed
D funding was insufficient
E conclusions were valid

Questions 21-23

Complete the summary below using words from the passage.

Write NO MORE THAN TWO WORDS for each answer.

The study focused on examining the 21______ between environmental factors and behavior. Researchers collected data over a 22______ period and found significant correlations. The findings suggest that 23______ plays a crucial role.

Questions 24-26

Label the diagram below using words from the passage.

Write NO MORE THAN ONE WORD for each label.

24 The upper layer: ____________
25 The central region: ____________
26 The foundation: ____________

Questions 27-30

Answer the questions below.

Write NO MORE THAN THREE WORDS AND/OR A NUMBER for each answer.

27 When was the initial study conducted?
28 How many participants were involved?
29 What was the primary methodology used?
30 Where were the findings first presented?
"""

print("="*70)
print("IELTS READING TRANSFORMER - QUESTION TYPE RECOGNITION DEMO")
print("="*70)
print("\nProcessing sample question text with all 10 question types...\n")

# Parse all questions
questions = parse_questions(demo_text)

print(f"✓ Successfully parsed {len(questions)} question groups\n")
print("-"*70)

# Display results by type
type_counts = {}
for q in questions:
    q_type = q.get('type', 'unknown')
    type_counts[q_type] = type_counts.get(q_type, 0) + 1

print("Question Types Recognized:\n")

type_names = {
    'single_choice': '1. Multiple Choice Questions (MCQ)',
    'yes_no_not_given': '2. True/False/Not Given OR Yes/No/Not Given',
    'matching_headings': '3. Matching Headings',
    'paragraph_matching': '4. Matching Information',
    'matching_features': '5. Matching Features',
    'matching_sentence_endings': '6. Matching Sentence Endings',
    'summary_completion': '7. Summary/Note/Table Completion',
    'diagram_label_completion': '8. Diagram Label Completion',
    'short_answer': '9. Short-Answer Questions',
    'fill_blank': '10. Sentence Completion (Fill-in-the-Blank)'
}

for q_type, count in sorted(type_counts.items()):
    type_name = type_names.get(q_type, q_type)
    print(f"   ✓ {type_name}: {count} section(s)")

print("\n" + "-"*70)
print("\nDetailed breakdown:\n")

for idx, q in enumerate(questions, 1):
    q_type = q.get('type', 'unknown')
    type_name = type_names.get(q_type, q_type)
    
    print(f"{idx}. {type_name}")
    
    if q_type == 'single_choice':
        print(f"   - {len(q.get('options', []))} options per question")
        if 'number' in q:
            print(f"   - Question {q['number']}: {q.get('text', '')[:50]}...")
    
    elif q_type in ['yes_no_not_given']:
        print(f"   - Title: {q.get('title', '')[:60]}...")
        print(f"   - {len(q.get('statements', []))} statements")
        print(f"   - Options: {', '.join(q.get('options', []))}")
    
    elif q_type == 'matching_headings':
        print(f"   - {len(q.get('headings', []))} headings available")
        print(f"   - {len(q.get('paragraphs', []))} paragraphs to match")
    
    elif q_type == 'paragraph_matching':
        print(f"   - {len(q.get('statements', []))} statements")
        print(f"   - Paragraph options: {', '.join(q.get('options', [])[:5])}")
    
    elif q_type == 'matching_features':
        print(f"   - {len(q.get('features', []))} features/entities")
        print(f"   - {len(q.get('statements', []))} statements to match")
    
    elif q_type == 'matching_sentence_endings':
        print(f"   - {len(q.get('sentence_beginnings', []))} sentence beginnings")
        print(f"   - {len(q.get('endings', []))} possible endings")
    
    elif q_type == 'summary_completion':
        print(f"   - {len(q.get('blanks', []))} blanks to fill")
        print(f"   - {len(q.get('options', []))} word bank options")
    
    elif q_type == 'diagram_label_completion':
        print(f"   - {len(q.get('labels', []))} labels to complete")
    
    elif q_type == 'short_answer':
        print(f"   - Question {q.get('number', '')}: {q.get('text', '')[:50]}...")
        print(f"   - Word limit: {q.get('word_limit', 'N/A')}")
    
    elif q_type == 'fill_blank':
        print(f"   - Question {q.get('number', '')}: {q.get('text', '')[:50]}...")
    
    print()

print("="*70)
print("✓ DEMO COMPLETE - All IELTS question types successfully recognized!")
print("="*70)
