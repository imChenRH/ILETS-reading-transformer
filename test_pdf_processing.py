#!/usr/bin/env python3
"""
Script to test PDF processing functionality
This will look for any PDF in common locations and process it
"""
import os
import sys
from pathlib import Path
import glob

# Add current directory to path
sys.path.insert(0, '/home/runner/work/ILETS-reading-transformer/ILETS-reading-transformer')

from app import extract_text_and_blocks, split_passage_questions, structure_passage, parse_questions, collect_passage_blocks, collect_question_blocks

def find_pdfs():
    """Find all PDF files in the repository"""
    base_path = Path('/home/runner/work/ILETS-reading-transformer/ILETS-reading-transformer')
    
    search_locations = [
        base_path / 'pdf',
        base_path / 'uploads',
        base_path,
        base_path / 'test_pdfs',
    ]
    
    pdfs = []
    for location in search_locations:
        if location.exists():
            pdfs.extend(location.glob('**/*.pdf'))
    
    return pdfs

def process_pdf(pdf_path):
    """Process a single PDF file"""
    print(f"\n{'='*70}")
    print(f"Processing: {pdf_path.name}")
    print('='*70)
    
    try:
        # Extract text and blocks
        print("\n1. Extracting text from PDF...")
        full_text, blocks = extract_text_and_blocks(pdf_path)
        print(f"   ✓ Extracted {len(full_text)} characters")
        print(f"   ✓ Found {len(blocks)} text blocks")
        
        # Split passage and questions
        print("\n2. Splitting passage from questions...")
        passage_text, questions_text = split_passage_questions(full_text)
        print(f"   ✓ Passage: {len(passage_text)} characters")
        print(f"   ✓ Questions: {len(questions_text)} characters")
        
        # Structure passage
        print("\n3. Structuring passage...")
        passage_blocks = collect_passage_blocks(passage_text, blocks)
        structured_passage = structure_passage(passage_text, passage_blocks)
        print(f"   ✓ Title: {structured_passage.get('title', 'N/A')[:60]}")
        print(f"   ✓ Paragraphs: {len(structured_passage.get('paragraphs', []))}")
        
        if structured_passage.get('paragraphs'):
            print("\n   Paragraph preview:")
            for p in structured_passage['paragraphs'][:3]:
                if p.get('letter'):
                    print(f"     {p['letter']}: {p['text'][:60]}...")
        
        # Parse questions
        print("\n4. Parsing questions...")
        question_blocks = collect_question_blocks(questions_text, blocks)
        parsed_questions = parse_questions(questions_text, blocks)
        print(f"   ✓ Total question groups: {len(parsed_questions)}")
        
        # Display question types
        print("\n5. Question types recognized:")
        type_counts = {}
        for q in parsed_questions:
            q_type = q.get('type', 'unknown')
            type_counts[q_type] = type_counts.get(q_type, 0) + 1
        
        question_type_names = {
            'matching_headings': 'Matching Headings',
            'yes_no_not_given': 'True/False/Not Given or Yes/No/Not Given',
            'short_answer': 'Short-Answer Questions',
            'fill_blank': 'Sentence Completion',
            'paragraph_matching': 'Matching Information',
            'matching_features': 'Matching Features',
            'matching_sentence_endings': 'Matching Sentence Endings',
            'diagram_label_completion': 'Diagram Label Completion',
            'summary_completion': 'Summary Completion',
            'single_choice': 'Multiple Choice Questions'
        }
        
        for q_type, count in sorted(type_counts.items()):
            type_name = question_type_names.get(q_type, q_type)
            print(f"   ✓ {type_name}: {count} section(s)")
        
        # Display sample questions
        print("\n6. Sample questions:")
        for idx, q in enumerate(parsed_questions[:3], 1):
            q_type = q.get('type', 'unknown')
            type_name = question_type_names.get(q_type, q_type)
            print(f"\n   Question Group {idx}: {type_name}")
            
            if q_type == 'single_choice':
                print(f"      Q{q.get('number', '')}: {q.get('text', '')[:50]}...")
                print(f"      Options: {len(q.get('options', []))} choices")
            elif q_type in ['yes_no_not_given']:
                print(f"      Title: {q.get('title', '')[:50]}...")
                print(f"      Statements: {len(q.get('statements', []))}")
            elif q_type == 'paragraph_matching':
                print(f"      Statements: {len(q.get('statements', []))}")
                print(f"      Options: {', '.join(q.get('options', [])[:5])}")
            elif q_type == 'matching_headings':
                print(f"      Headings: {len(q.get('headings', []))}")
                print(f"      Paragraphs: {len(q.get('paragraphs', []))}")
            elif q_type == 'short_answer':
                print(f"      Q{q.get('number', '')}: {q.get('text', '')[:50]}...")
                print(f"      Word limit: {q.get('word_limit', 'N/A')}")
        
        print(f"\n{'='*70}")
        print(f"✓ Successfully processed: {pdf_path.name}")
        print('='*70)
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error processing PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("="*70)
    print("IELTS PDF PROCESSOR - Looking for PDF files...")
    print("="*70)
    
    pdfs = find_pdfs()
    
    if not pdfs:
        print("\n⚠ No PDF files found in:")
        print("  - pdf/")
        print("  - uploads/")
        print("  - repository root")
        print("  - test_pdfs/")
        print("\nPlease upload a PDF file to one of these locations.")
        print("\nYou can also specify a PDF path as an argument:")
        print("  python test_pdf_processing.py path/to/your/file.pdf")
        return
    
    print(f"\nFound {len(pdfs)} PDF file(s):\n")
    for i, pdf in enumerate(pdfs, 1):
        print(f"  {i}. {pdf.relative_to(Path('/home/runner/work/ILETS-reading-transformer/ILETS-reading-transformer'))}")
    
    # Process each PDF
    success_count = 0
    for pdf in pdfs:
        if process_pdf(pdf):
            success_count += 1
    
    print(f"\n{'='*70}")
    print(f"SUMMARY: Processed {success_count}/{len(pdfs)} PDF(s) successfully")
    print('='*70)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Process specific PDF from command line argument
        pdf_path = Path(sys.argv[1])
        if pdf_path.exists():
            process_pdf(pdf_path)
        else:
            print(f"Error: PDF file not found: {pdf_path}")
    else:
        main()
