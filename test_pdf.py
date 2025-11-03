import glob
import re

import fitz

from app import parse_questions


def extract_text_and_blocks(pdf_path: str):
    text = ''
    blocks = []
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            text += page.get_text() + "\n"
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                if "lines" not in block:
                    continue
                block_text = "".join(
                    span["text"]
                    for line in block["lines"]
                    for span in line.get("spans", [])
                )
                if not block_text.strip():
                    continue
                blocks.append({
                    "page_index": page_index,
                    "bbox": block.get("bbox"),
                    "text": block_text
                })
    return text, blocks


def split_passage_questions(full_text: str):
    passage = ""
    questions = ""
    passage_start = re.search(r'below\.', full_text, re.IGNORECASE)
    if passage_start:
        passage_start_index = passage_start.end()
        question_keywords = [
            "Choose the correct letter",
            "Complete the sentences",
            "Complete the summary",
            "Do the following statements agree",
            "Matching",
            "List of Headings",
            r'\d+\s+What'
        ]
        question_start_index = -1
        for keyword in question_keywords:
            search_result = re.search(keyword, full_text[passage_start_index:], re.IGNORECASE)
            if search_result:
                absolute = passage_start_index + search_result.start()
                if question_start_index == -1 or absolute < question_start_index:
                    question_start_index = absolute
        if question_start_index != -1:
            passage = full_text[passage_start_index:question_start_index]
            questions = full_text[question_start_index:]
        else:
            passage = full_text[passage_start_index:]
            questions = full_text[passage_start_index:]
    else:
        passage = full_text
        questions = full_text
    return passage, questions


def main():
    candidates = [path for path in glob.glob('pdf/*.pdf') if 'Piraha' in path]
    if not candidates:
        raise FileNotFoundError("Unable to locate the Pirahã PDF inside pdf/ directory")
    pdf_path = candidates[0]

    text, blocks = extract_text_and_blocks(pdf_path)
    passage, question_text = split_passage_questions(text)
    parsed_questions = parse_questions(question_text, blocks)

    print("Passage preview:")
    print(passage[:300] + "..." if len(passage) > 300 else passage)
    print("\nParsed Questions:")
    for question in parsed_questions:
        if question['type'] == 'single_choice':
            print(f"Single Choice {question['number']}. {question['text']}")
            for idx, option in enumerate(question['options'], start=1):
                print(f"   {chr(64 + idx)}. {option}")
        elif question['type'] == 'summary_completion':
            print("Summary Completion:")
            print(question['text'])
            print(f"Blanks: {question['blanks']}")
            print("Options:")
            for option in question['options']:
                print(f"   {option['key']}: {option['text']}")
        print()


if __name__ == '__main__':
    main()
