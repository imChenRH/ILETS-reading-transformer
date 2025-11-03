#!/usr/bin/env python3
"""
Extended test to validate fixes with MORE PDF files.
Tests 10+ different PDFs to ensure robustness across various formats.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import (
    extract_text_and_blocks,
    split_passage_questions,
    structure_passage,
    collect_passage_blocks,
    parse_questions,
)


def test_single_pdf(pdf_path: Path, test_name: str):
    """Test a single PDF and return results."""
    if not pdf_path.exists():
        return {
            'name': test_name,
            'status': 'SKIPPED',
            'reason': 'File not found'
        }
    
    try:
        # Extract and parse
        full_text, blocks = extract_text_and_blocks(str(pdf_path))
        passage, question_text = split_passage_questions(full_text)
        passage_blocks = collect_passage_blocks(passage, blocks)
        structured_passage = structure_passage(passage, passage_blocks)
        parsed_questions = parse_questions(question_text, blocks)
        
        # Collect question numbers
        question_numbers = set()
        question_types = {}
        
        for q in parsed_questions:
            q_type = q.get('type')
            question_types[q_type] = question_types.get(q_type, 0) + 1
            
            if q_type == 'single_choice':
                num = q.get('number')
                if num:
                    if num in question_numbers:
                        return {
                            'name': test_name,
                            'status': 'FAILED',
                            'reason': f'Duplicate question number {num} in {q_type}'
                        }
                    question_numbers.add(num)
            elif q_type in ['paragraph_matching', 'yes_no_not_given', 'matching_features', 
                            'matching_sentence_endings', 'matching_headings']:
                statements = q.get('statements', []) or q.get('sentence_beginnings', []) or q.get('paragraphs', [])
                for stmt in statements:
                    num = stmt.get('number')
                    if num:
                        if num in question_numbers:
                            return {
                                'name': test_name,
                                'status': 'FAILED',
                                'reason': f'Duplicate question number {num} in {q_type}'
                            }
                        question_numbers.add(num)
            elif q_type == 'fill_blank':
                num = q.get('number')
                if num:
                    if num in question_numbers:
                        return {
                            'name': test_name,
                            'status': 'FAILED',
                            'reason': f'Duplicate question number {num} in {q_type}'
                        }
                    question_numbers.add(num)
            elif q_type == 'summary_completion':
                for num in q.get('blanks', []):
                    if num in question_numbers:
                        return {
                            'name': test_name,
                            'status': 'FAILED',
                            'reason': f'Duplicate question number {num} in {q_type}'
                        }
                    question_numbers.add(num)
            elif q_type == 'short_answer':
                num = q.get('number')
                if num:
                    if num in question_numbers:
                        return {
                            'name': test_name,
                            'status': 'FAILED',
                            'reason': f'Duplicate question number {num} in {q_type}'
                        }
                    question_numbers.add(num)
        
        # Check for standalone subheadings
        standalone_subheadings = []
        subheading_keywords = [
            'description of the study',
            'methodological issues',
            'lessons to consider',
            'conclusion',
            'introduction',
            'background',
            'discussion',
            'results',
            'methods',
        ]
        
        for para in structured_passage['paragraphs']:
            text = para['text'].lower().strip()
            if len(para['text']) < 50:
                for keyword in subheading_keywords:
                    if text == keyword:
                        standalone_subheadings.append(para['text'])
        
        if standalone_subheadings:
            return {
                'name': test_name,
                'status': 'FAILED',
                'reason': f'Found {len(standalone_subheadings)} standalone subheadings: {standalone_subheadings[:2]}'
            }
        
        return {
            'name': test_name,
            'status': 'PASSED',
            'question_count': len(question_numbers),
            'paragraph_count': len(structured_passage['paragraphs']),
            'question_types': question_types,
        }
        
    except Exception as e:
        return {
            'name': test_name,
            'status': 'ERROR',
            'reason': str(e)
        }


def run_extended_tests():
    """Test multiple PDFs to ensure robustness."""
    print("\n" + "="*80)
    print("EXTENDED PDF TESTING - Testing Multiple PDF Files")
    print("="*80)
    
    base_path = Path(__file__).parent / "pdf/ZYZ老师文章合集（至10.6）[164篇]"
    
    # Test cases with various PDFs
    test_cases = [
        ("92. P3 - The Pirahã people of Brazil  巴西皮拉罕部落语言【高】.pdf", "Pirahã - Complex mixed questions"),
        ("60. P3 - A closer examination of a study on verbal and non-verbal messages 语言表达研究【高】.pdf", "Verbal Messages - Subheadings"),
        ("70. P3 - Insect-inspired robots 昆虫机器人【高】.pdf", "Insect Robots - Paragraph matching"),
        ("89. P3 - The Fruit Book 果实之书【高】.pdf", "Fruit Book - Fill blanks"),
        ("65. P3 - Does class size matter 课堂规模【高】.pdf", "Class Size - Simple questions"),
        ("101. P3 - Yawning 打呵欠【高】.pdf", "Yawning"),
        ("111. P3 - Whale Culture 鲸鱼文化【高】.pdf", "Whale Culture"),
        ("123. P3 - Images and Places 风景与印记 【高】.pdf", "Images and Places"),
        ("127. P3 - Science and Filmmaking 电影科学(CGI)【高】.pdf", "Science and Filmmaking"),
        ("147. P3 - Movement Underwater 水下运动【高】.pdf", "Movement Underwater"),
        ("61. P3 - Book Review The Discovery of Slowness 富兰克林(慢的发现)【高】.pdf", "Book Review"),
        ("66. P3 - Elephant Communication 大象交流【高】.pdf", "Elephant Communication"),
        ("67. P3 - Flower Power 鲜花的力量(花之力)【高】.pdf", "Flower Power"),
        ("76. P3 - Living dunes 流动沙丘【高】.pdf", "Living Dunes"),
        ("81. P3 - Robert Louis Stevenson 苏格兰作家【高】.pdf", "Robert Louis Stevenson"),
    ]
    
    results = []
    for pdf_file, test_name in test_cases:
        pdf_path = base_path / pdf_file
        print(f"\nTesting: {test_name}")
        print(f"  File: {pdf_file}")
        result = test_single_pdf(pdf_path, test_name)
        results.append(result)
        
        if result['status'] == 'PASSED':
            print(f"  ✅ PASS - {result['question_count']} questions, {result['paragraph_count']} paragraphs")
            if result.get('question_types'):
                types_str = ', '.join(f"{k}:{v}" for k, v in sorted(result['question_types'].items()))
                print(f"  Question types: {types_str}")
        elif result['status'] == 'SKIPPED':
            print(f"  ⚠️  SKIPPED - {result['reason']}")
        elif result['status'] == 'FAILED':
            print(f"  ❌ FAILED - {result['reason']}")
        elif result['status'] == 'ERROR':
            print(f"  ❌ ERROR - {result['reason']}")
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for r in results if r['status'] == 'PASSED')
    failed = sum(1 for r in results if r['status'] == 'FAILED')
    error = sum(1 for r in results if r['status'] == 'ERROR')
    skipped = sum(1 for r in results if r['status'] == 'SKIPPED')
    total = len(results)
    
    print(f"\n✅ Passed:  {passed}")
    print(f"❌ Failed:  {failed}")
    print(f"⚠️  Errors:  {error}")
    print(f"⚠️  Skipped: {skipped}")
    print(f"Total:     {total}")
    
    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if r['status'] == 'FAILED':
                print(f"  - {r['name']}: {r['reason']}")
    
    if error > 0:
        print("\nError tests:")
        for r in results:
            if r['status'] == 'ERROR':
                print(f"  - {r['name']}: {r['reason']}")
    
    success_rate = (passed / (total - skipped) * 100) if (total - skipped) > 0 else 0
    print(f"\nSuccess rate: {success_rate:.1f}% ({passed}/{total - skipped} non-skipped tests)")
    
    if failed == 0 and error == 0:
        print("\n🎉 ALL TESTS PASSED! The fixes work correctly across all tested PDFs.")
        return 0
    else:
        print(f"\n⚠️  Some tests failed. Please review the issues above.")
        return 1


if __name__ == '__main__':
    exit_code = run_extended_tests()
    sys.exit(exit_code)
