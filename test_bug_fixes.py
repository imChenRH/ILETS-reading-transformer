#!/usr/bin/env python3
"""
Test to validate fixes for title type matching, subheading identification,
and question type misidentification issues.

This test verifies that:
1. Questions are not duplicated between different question types
2. Subheadings in passages are merged with their content, not treated as separate paragraphs
3. Question numbers are correctly extracted from MCQ questions
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app import (
    extract_text_and_blocks,
    split_passage_questions,
    structure_passage,
    collect_passage_blocks,
    parse_questions,
    parse_single_choice,
    parse_yes_no_not_given,
    parse_matching_sentence_endings,
)


def test_no_duplicate_question_numbers():
    """Test that question numbers are not duplicated across different question types."""
    print("\n" + "="*80)
    print("TEST 1: No Duplicate Question Numbers")
    print("="*80)
    
    # Test with the Pirahã PDF that had duplicate questions 37-40
    pdf_path = Path(__file__).parent / "pdf/ZYZ老师文章合集（至10.6）[164篇]/92. P3 - The Pirahã people of Brazil  巴西皮拉罕部落语言【高】.pdf"
    
    if not pdf_path.exists():
        print("⚠️  Test PDF not found, skipping test")
        return True
    
    full_text, blocks = extract_text_and_blocks(str(pdf_path))
    passage, question_text = split_passage_questions(full_text)
    parsed_questions = parse_questions(question_text, blocks)
    
    # Collect all question numbers
    question_numbers = []
    for q in parsed_questions:
        q_type = q.get('type')
        if q_type == 'single_choice':
            question_numbers.append((q.get('number'), q_type))
        elif q_type in ['paragraph_matching', 'yes_no_not_given', 'matching_features', 
                        'matching_sentence_endings', 'matching_headings']:
            statements = q.get('statements', []) or q.get('sentence_beginnings', []) or q.get('paragraphs', [])
            for stmt in statements:
                question_numbers.append((stmt.get('number'), q_type))
        elif q_type == 'fill_blank':
            question_numbers.append((q.get('number'), q_type))
        elif q_type == 'summary_completion':
            for num in q.get('blanks', []):
                question_numbers.append((num, q_type))
        elif q_type == 'short_answer':
            question_numbers.append((q.get('number'), q_type))
    
    # Check for duplicates
    seen = {}
    duplicates = []
    for num, q_type in question_numbers:
        if num in seen:
            duplicates.append((num, seen[num], q_type))
            print(f"❌ DUPLICATE: Question {num} found in both {seen[num]} and {q_type}")
        else:
            seen[num] = q_type
    
    if not duplicates:
        print(f"✅ PASS: No duplicate question numbers found")
        print(f"   Total questions parsed: {len(question_numbers)}")
        return True
    else:
        print(f"❌ FAIL: Found {len(duplicates)} duplicate question numbers")
        return False


def test_subheading_merging():
    """Test that subheadings are properly merged with their following content."""
    print("\n" + "="*80)
    print("TEST 2: Subheading Merging")
    print("="*80)
    
    # Test with the verbal/non-verbal messages PDF that had subheading issues
    pdf_path = Path(__file__).parent / "pdf/ZYZ老师文章合集（至10.6）[164篇]/60. P3 - A closer examination of a study on verbal and non-verbal messages 语言表达研究【高】.pdf"
    
    if not pdf_path.exists():
        print("⚠️  Test PDF not found, skipping test")
        return True
    
    full_text, blocks = extract_text_and_blocks(str(pdf_path))
    passage, question_text = split_passage_questions(full_text)
    passage_blocks = collect_passage_blocks(passage, blocks)
    structured_passage = structure_passage(passage, passage_blocks)
    
    # Check that common subheadings are not standalone paragraphs
    standalone_subheadings = []
    subheading_keywords = [
        'description of the study',
        'methodological issues',
        'lessons to consider',
        'conclusion',
    ]
    
    for i, para in enumerate(structured_passage['paragraphs']):
        text = para['text'].lower()
        # Check if this is a very short paragraph that matches a subheading pattern
        if len(para['text']) < 50:
            for keyword in subheading_keywords:
                if keyword in text and text.strip() == keyword:
                    standalone_subheadings.append((i, para['text']))
                    print(f"❌ STANDALONE SUBHEADING: Paragraph {i}: '{para['text']}'")
    
    if not standalone_subheadings:
        print(f"✅ PASS: No standalone subheadings found")
        print(f"   Total paragraphs: {len(structured_passage['paragraphs'])}")
        
        # Verify that subheadings are merged
        merged_count = 0
        for para in structured_passage['paragraphs']:
            for keyword in subheading_keywords:
                if para['text'].lower().startswith(keyword):
                    # Check if there's content after the subheading
                    if len(para['text']) > len(keyword) + 10:
                        merged_count += 1
                        print(f"   ✓ Subheading merged: '{para['text'][:60]}...'")
        
        if merged_count > 0:
            print(f"   Found {merged_count} properly merged subheadings")
        
        return True
    else:
        print(f"❌ FAIL: Found {len(standalone_subheadings)} standalone subheadings")
        return False


def test_mcq_number_extraction():
    """Test that MCQ question numbers are correctly extracted."""
    print("\n" + "="*80)
    print("TEST 3: MCQ Number Extraction")
    print("="*80)
    
    # Test with the Pirahã PDF
    pdf_path = Path(__file__).parent / "pdf/ZYZ老师文章合集（至10.6）[164篇]/92. P3 - The Pirahã people of Brazil  巴西皮拉罕部落语言【高】.pdf"
    
    if not pdf_path.exists():
        print("⚠️  Test PDF not found, skipping test")
        return True
    
    full_text, blocks = extract_text_and_blocks(str(pdf_path))
    passage, question_text = split_passage_questions(full_text)
    mcqs = parse_single_choice(question_text)
    
    # Expected question numbers for this PDF: 27-32
    expected_numbers = ['27', '28', '29', '30', '31', '32']
    actual_numbers = [q['number'] for q in mcqs]
    
    print(f"   Expected: {expected_numbers}")
    print(f"   Actual:   {actual_numbers}")
    
    errors = []
    
    # Check if all expected numbers are found
    for num in expected_numbers:
        if num not in actual_numbers:
            errors.append(f"Missing question {num}")
            print(f"❌ Missing question {num}")
    
    # Check if there are any unexpected numbers
    for num in actual_numbers:
        if num not in expected_numbers:
            errors.append(f"Unexpected question {num}")
            print(f"❌ Unexpected question {num}")
    
    # Check that question text doesn't start with a number (shouldn't have leftover numbers)
    for q in mcqs:
        if q['text'] and q['text'][0].isdigit():
            errors.append(f"Question {q['number']} text starts with digit: '{q['text'][:50]}'")
            print(f"❌ Question {q['number']} text starts with digit: '{q['text'][:50]}...'")
    
    if not errors:
        print(f"✅ PASS: All MCQ questions correctly parsed")
        return True
    else:
        print(f"❌ FAIL: Found {len(errors)} errors in MCQ parsing")
        return False


def test_yes_no_vs_sentence_endings():
    """Test that Yes/No/Not Given questions are not misidentified as sentence endings."""
    print("\n" + "="*80)
    print("TEST 4: Yes/No vs Sentence Endings Distinction")
    print("="*80)
    
    # Sample text with Yes/No/Not Given questions
    test_text = """
Questions 37-40

Do the following statements agree with the views of the writer?

Write YES, NO, or NOT GIVEN

37 The theory was widely accepted.
38 Further research is needed.
39 The method has been criticized.
40 Results were inconclusive.
A present
B past
C future
D time
"""
    
    sentence_endings = parse_matching_sentence_endings(test_text)
    yes_no = parse_yes_no_not_given(test_text)
    
    print(f"   Sentence endings found: {len(sentence_endings)}")
    print(f"   Yes/No/Not Given found: {len(yes_no)}")
    
    if len(sentence_endings) > 0:
        print(f"❌ FAIL: Yes/No questions incorrectly parsed as sentence endings")
        return False
    elif len(yes_no) == 1:
        print(f"✅ PASS: Yes/No questions correctly identified")
        return True
    else:
        print(f"⚠️  WARNING: Expected 1 Yes/No section, found {len(yes_no)}")
        return False


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "="*80)
    print("RUNNING COMPREHENSIVE TESTS FOR BUG FIXES")
    print("="*80)
    
    tests = [
        ("No Duplicate Question Numbers", test_no_duplicate_question_numbers),
        ("Subheading Merging", test_subheading_merging),
        ("MCQ Number Extraction", test_mcq_number_extraction),
        ("Yes/No vs Sentence Endings", test_yes_no_vs_sentence_endings),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ TEST FAILED WITH EXCEPTION: {name}")
            print(f"   {str(e)}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Issues have been fixed.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    exit_code = run_all_tests()
    sys.exit(exit_code)
