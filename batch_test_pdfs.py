#!/usr/bin/env python3
"""
Comprehensive batch test program for IELTS Reading PDFs.
Tests all PDFs to identify potential bugs in:
1. Left side formatting (titles, instructions, paragraph structure)
2. Right side questions (completeness, type recognition, no mixing)
3. Special attention to matching heading question types
"""
import sys
import json
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict

from app import (
    extract_text_and_blocks,
    split_passage_questions,
    structure_passage,
    collect_passage_blocks,
    parse_questions,
)
from constants import SUBHEADING_KEYWORDS


class PDFTestResult:
    """Container for test results for a single PDF."""
    
    def __init__(self, filename: str):
        self.filename = filename
        self.passed = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: Dict[str, Any] = {}
        
    def add_error(self, message: str):
        """Add a critical error (test fails)."""
        self.errors.append(message)
        self.passed = False
        
    def add_warning(self, message: str):
        """Add a warning (test passes but needs attention)."""
        self.warnings.append(message)
        
    def add_info(self, key: str, value: Any):
        """Add informational data."""
        self.info[key] = value


def test_left_side_formatting(structured_passage: Dict[str, Any], result: PDFTestResult):
    """
    Test left side (passage) formatting.
    Checks: title recognition, paragraph structure, no instruction leakage.
    """
    # Check title
    title = structured_passage.get('title', '')
    if not title:
        result.add_error("LEFT: No title detected")
    elif len(title) < 5:
        result.add_warning(f"LEFT: Title seems too short: '{title}'")
    elif len(title) > 150:
        result.add_warning(f"LEFT: Title seems too long ({len(title)} chars): '{title[:60]}...'")
    
    # Check for instruction leakage in title
    instruction_keywords = [
        'reading passage', 'questions', 'you should spend',
        'choose the correct', 'complete the', 'match the'
    ]
    title_lower = title.lower()
    for keyword in instruction_keywords:
        if keyword in title_lower:
            result.add_error(f"LEFT: Title contains instruction keyword '{keyword}': '{title}'")
    
    result.add_info('title', title)
    
    # Check paragraphs
    paragraphs = structured_passage.get('paragraphs', [])
    if not paragraphs:
        result.add_error("LEFT: No paragraphs detected")
    elif len(paragraphs) < 3:
        result.add_warning(f"LEFT: Only {len(paragraphs)} paragraphs detected (expected 5-15)")
    
    result.add_info('paragraph_count', len(paragraphs))
    
    # Check paragraph letters (for matching heading questions)
    lettered_paras = [p for p in paragraphs if p.get('letter')]
    if lettered_paras:
        letters = [p['letter'] for p in lettered_paras]
        result.add_info('paragraph_letters', letters)
        
        # Check for gaps in lettering
        if letters:
            expected_letters = []
            for i in range(len(letters)):
                expected_letters.append(chr(ord('A') + i))
            
            if letters != expected_letters:
                result.add_warning(f"LEFT: Paragraph letters not sequential: {letters} (expected: {expected_letters})")
    
    # Check for standalone subheadings (common bug)
    standalone_subheadings = []
    
    for para in paragraphs:
        text = para.get('text', '').strip()
        if len(text) < 60:  # Short paragraphs might be subheadings
            text_lower = text.lower()
            for keyword in SUBHEADING_KEYWORDS:
                if keyword in text_lower and len(text) < 100:
                    standalone_subheadings.append(text)
                    break
    
    if standalone_subheadings:
        result.add_error(f"LEFT: Found {len(standalone_subheadings)} standalone subheadings: {standalone_subheadings[:2]}")
        result.add_info('standalone_subheadings', standalone_subheadings)


def test_right_side_questions(parsed_questions: List[Dict[str, Any]], result: PDFTestResult):
    """
    Test right side (questions) formatting.
    Checks: question completeness, type recognition, no mixing, duplicate detection.
    """
    if not parsed_questions:
        result.add_error("RIGHT: No questions detected")
        return
    
    result.add_info('question_count', len(parsed_questions))
    
    # Count question types
    question_types = defaultdict(int)
    for q in parsed_questions:
        q_type = q.get('type', 'unknown')
        question_types[q_type] += 1
    
    result.add_info('question_types', dict(question_types))
    
    # Check for unknown types
    if 'unknown' in question_types:
        result.add_error(f"RIGHT: {question_types['unknown']} questions with unknown type")
    
    # Collect all question numbers
    question_numbers: Set[str] = set()
    duplicate_numbers: List[str] = []
    
    for q in parsed_questions:
        q_type = q.get('type')
        
        # Extract numbers based on question type
        if q_type == 'single_choice':
            num = q.get('number')
            if num:
                if num in question_numbers:
                    duplicate_numbers.append(num)
                question_numbers.add(num)
        
        elif q_type == 'fill_blank':
            num = q.get('number')
            if num:
                if num in question_numbers:
                    duplicate_numbers.append(num)
                question_numbers.add(num)
        
        elif q_type == 'short_answer':
            num = q.get('number')
            if num:
                if num in question_numbers:
                    duplicate_numbers.append(num)
                question_numbers.add(num)
        
        elif q_type in ['paragraph_matching', 'yes_no_not_given', 'matching_features', 
                        'matching_sentence_endings']:
            statements = q.get('statements', [])
            for stmt in statements:
                num = stmt.get('number')
                if num:
                    if num in question_numbers:
                        duplicate_numbers.append(num)
                    question_numbers.add(num)
        
        elif q_type == 'matching_headings':
            paragraphs = q.get('paragraphs', [])
            for para in paragraphs:
                num = para.get('number')
                if num:
                    if num in question_numbers:
                        duplicate_numbers.append(num)
                    question_numbers.add(num)
        
        elif q_type == 'summary_completion':
            for num in q.get('blanks', []):
                if num in question_numbers:
                    duplicate_numbers.append(num)
                question_numbers.add(num)
        
        elif q_type == 'diagram_label_completion':
            labels = q.get('labels', [])
            for label in labels:
                num = label.get('number')
                if num:
                    if num in question_numbers:
                        duplicate_numbers.append(num)
                    question_numbers.add(num)
    
    # Report duplicates
    if duplicate_numbers:
        result.add_error(f"RIGHT: Duplicate question numbers detected: {duplicate_numbers}")
    
    result.add_info('total_questions', len(question_numbers))
    result.add_info('question_numbers', sorted([int(n) for n in question_numbers if n.isdigit()]))


def test_matching_headings_special(parsed_questions: List[Dict[str, Any]], 
                                   structured_passage: Dict[str, Any],
                                   result: PDFTestResult):
    """
    Special tests for matching headings question type.
    This is a common source of bugs with titles/instructions.
    """
    matching_heading_questions = [q for q in parsed_questions if q.get('type') == 'matching_headings']
    
    if not matching_heading_questions:
        return  # No matching headings in this PDF
    
    for mh_q in matching_heading_questions:
        # Check that headings exist
        headings = mh_q.get('headings', [])
        if not headings:
            result.add_error("MATCHING HEADINGS: No headings (roman numerals) found")
        else:
            result.add_info('matching_headings_count', len(headings))
            
            # Check heading format (should have roman numerals)
            for heading in headings[:3]:  # Check first few
                key = heading.get('key', '')
                if not key:
                    result.add_warning("MATCHING HEADINGS: Heading missing roman numeral key")
        
        # Check that paragraphs exist
        paragraphs = mh_q.get('paragraphs', [])
        if not paragraphs:
            result.add_error("MATCHING HEADINGS: No paragraph mappings found")
        else:
            # Verify paragraph letters match passage structure
            passage_letters = [p.get('letter') for p in structured_passage.get('paragraphs', []) 
                             if p.get('letter')]
            question_letters = [p.get('letter') for p in paragraphs]
            
            # Check if question letters are subset of passage letters
            for qletter in question_letters:
                if qletter not in passage_letters:
                    result.add_warning(f"MATCHING HEADINGS: Question references paragraph '{qletter}' "
                                     f"not found in passage (passage has: {passage_letters})")
        
        # Check instructions
        instructions = mh_q.get('instructions', [])
        if not instructions:
            result.add_warning("MATCHING HEADINGS: No instructions found")


def test_single_pdf(pdf_path: Path) -> PDFTestResult:
    """Test a single PDF file."""
    result = PDFTestResult(pdf_path.name)
    
    try:
        # Extract and parse
        full_text, blocks = extract_text_and_blocks(str(pdf_path))
        passage, question_text = split_passage_questions(full_text)
        passage_blocks = collect_passage_blocks(passage, blocks)
        structured_passage = structure_passage(passage, passage_blocks)
        parsed_questions = parse_questions(question_text, blocks)
        
        # Run tests
        test_left_side_formatting(structured_passage, result)
        test_right_side_questions(parsed_questions, result)
        test_matching_headings_special(parsed_questions, structured_passage, result)
        
    except Exception as e:
        result.add_error(f"EXCEPTION: {type(e).__name__}: {str(e)[:200]}")
    
    return result


def run_batch_test(pdf_dir: Path = None, max_pdfs: int = None, verbose: bool = False):
    """
    Run batch test on all PDFs in the directory.
    
    Args:
        pdf_dir: Directory containing PDFs (default: ./pdf)
        max_pdfs: Maximum number of PDFs to test (default: all)
        verbose: Show detailed output for each PDF
    """
    if pdf_dir is None:
        pdf_dir = Path(__file__).parent / "pdf"
    
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    
    if max_pdfs:
        pdf_files = pdf_files[:max_pdfs]
    
    print(f"\n{'='*80}")
    print(f"BATCH PDF TESTING - Testing {len(pdf_files)} PDFs")
    print(f"{'='*80}\n")
    
    results: List[PDFTestResult] = []
    
    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] Testing: {pdf_file.name[:70]}")
        
        result = test_single_pdf(pdf_file)
        results.append(result)
        
        if verbose or not result.passed:
            # Show details for failed tests or in verbose mode
            if result.errors:
                for error in result.errors:
                    print(f"    ❌ {error}")
            if result.warnings:
                for warning in result.warnings:
                    print(f"    ⚠️  {warning}")
            if result.passed and not result.warnings:
                print(f"    ✅ PASSED")
        else:
            # Just show status
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"    {status}")
    
    # Summary
    print(f"\n{'='*80}")
    print("BATCH TEST SUMMARY")
    print(f"{'='*80}\n")
    
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)
    
    print(f"✅ Passed:  {passed}/{total} ({100*passed/total:.1f}%)")
    print(f"❌ Failed:  {failed}/{total} ({100*failed/total:.1f}%)")
    
    # Category breakdown
    print(f"\n{'='*80}")
    print("ISSUES BY CATEGORY")
    print(f"{'='*80}\n")
    
    category_counts = defaultdict(int)
    for result in results:
        for error in result.errors:
            if error.startswith('LEFT:'):
                category_counts['Left Side (Passage)'] += 1
            elif error.startswith('RIGHT:'):
                category_counts['Right Side (Questions)'] += 1
            elif error.startswith('MATCHING HEADINGS:'):
                category_counts['Matching Headings'] += 1
            else:
                category_counts['Other'] += 1
    
    for category, count in sorted(category_counts.items()):
        print(f"{category}: {count} issues")
    
    # Detailed error report
    if failed > 0:
        print(f"\n{'='*80}")
        print("FAILED TESTS DETAILS")
        print(f"{'='*80}\n")
        
        for result in results:
            if not result.passed:
                print(f"\n📄 {result.filename}")
                for error in result.errors:
                    print(f"   ❌ {error}")
                if result.warnings:
                    for warning in result.warnings:
                        print(f"   ⚠️  {warning}")
                if result.info:
                    print(f"   ℹ️  Info: {result.info}")
    
    # Warning summary
    warnings_count = sum(len(r.warnings) for r in results)
    if warnings_count > 0:
        print(f"\n{'='*80}")
        print(f"WARNINGS SUMMARY ({warnings_count} total)")
        print(f"{'='*80}\n")
        
        warning_types = defaultdict(int)
        for result in results:
            for warning in result.warnings:
                # Extract warning type (first part before colon)
                warning_type = warning.split(':', 1)[0] if ':' in warning else warning[:50]
                warning_types[warning_type] += 1
        
        for wtype, count in sorted(warning_types.items(), key=lambda x: -x[1]):
            print(f"{wtype}: {count} occurrences")
    
    print(f"\n{'='*80}")
    print("STATISTICS")
    print(f"{'='*80}\n")
    
    # Question type statistics
    all_question_types = defaultdict(int)
    for result in results:
        q_types = result.info.get('question_types', {})
        for qtype, count in q_types.items():
            all_question_types[qtype] += count
    
    print("Question types across all PDFs:")
    for qtype, count in sorted(all_question_types.items(), key=lambda x: -x[1]):
        print(f"  {qtype}: {count}")
    
    return results, passed, failed


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch test IELTS Reading PDFs')
    parser.add_argument('--max', type=int, help='Maximum number of PDFs to test')
    parser.add_argument('--verbose', action='store_true', help='Show detailed output')
    parser.add_argument('--json', type=str, help='Save results to JSON file')
    
    args = parser.parse_args()
    
    results, passed, failed = run_batch_test(max_pdfs=args.max, verbose=args.verbose)
    
    if args.json:
        # Save results to JSON
        json_data = []
        for result in results:
            json_data.append({
                'filename': result.filename,
                'passed': result.passed,
                'errors': result.errors,
                'warnings': result.warnings,
                'info': result.info
            })
        
        with open(args.json, 'w') as f:
            json.dump(json_data, f, indent=2)
        print(f"\n✅ Results saved to {args.json}")
    
    sys.exit(0 if failed == 0 else 1)
