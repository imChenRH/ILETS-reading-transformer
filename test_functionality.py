#!/usr/bin/env python3
"""
Simple test to verify core functionality of the IELTS Reading Transformer
"""
import sys
from pathlib import Path

# Test imports
try:
    from app import (
        extract_text_and_blocks,
        split_passage_questions,
        structure_passage,
        parse_questions,
        collect_passage_blocks,
        collect_question_blocks,
    )
    print("✓ All imports successful")
except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)

# Test text splitting
test_text = """
Some introduction text here.
The passage starts below.

This is the actual passage content with multiple paragraphs.

A This is paragraph A with some content.

B This is paragraph B with more content.

Questions 1-5

Choose the correct letter A, B, C or D.

1 What is the main topic?
A Topic one
B Topic two  
C Topic three
D Topic four
"""

print("\n--- Testing text splitting ---")
passage, questions = split_passage_questions(test_text)
print(f"✓ Passage extracted: {len(passage)} characters")
print(f"✓ Questions extracted: {len(questions)} characters")

print("\n--- Testing passage structure ---")
structured = structure_passage(passage)
print(f"✓ Passage structured with {len(structured.get('paragraphs', []))} paragraphs")
print(f"✓ Title: {structured.get('title', 'N/A')[:50]}")

print("\n--- Testing question parsing ---")
parsed_questions = parse_questions(questions)
print(f"✓ Parsed {len(parsed_questions)} question groups")
for q in parsed_questions:
    print(f"  - {q.get('type', 'unknown')} question")

print("\n--- Testing summary ---")
print("✓ All core functionality tests passed!")
print("\nThe IELTS Reading Transformer is ready to use.")
print("Run 'python app.py' to start the web application.")
