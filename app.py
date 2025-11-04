import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from flask import Flask, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from constants import SUBHEADING_KEYWORDS

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.config['SECRET_KEY'] = 'supersecretkey'


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def extract_text_and_blocks(filepath: Path) -> Tuple[str, List[Dict[str, Any]]]:
    text_chunks: List[str] = []
    blocks: List[Dict[str, Any]] = []

    with fitz.open(filepath) as doc:
        for page_index, page in enumerate(doc):
            text_chunks.append(page.get_text())
            page_dict = page.get_text('dict')
            for block in page_dict.get('blocks', []):
                if block.get('type', 0) != 0:
                    continue
                lines = block.get('lines')
                if not lines:
                    continue
                block_text = ''.join(
                    span.get('text', '')
                    for line in lines
                    for span in line.get('spans', [])
                )
                if block_text.strip():
                    blocks.append({
                        'page_index': page_index,
                        'bbox': block.get('bbox'),
                        'text': block_text
                    })

    return '\n'.join(text_chunks), blocks


def split_passage_questions(full_text: str) -> Tuple[str, str]:
    """
    Split the full text into passage and questions.
    Handles multiple formats:
    1. Standard: passage followed by questions
    2. Matching Headings: questions (with List of Headings) then passage title, then more questions
    3. Reading Passage header followed by title and content, then questions
    """
    passage = full_text
    questions = ''

    # Check for "List of Headings" pattern - indicates Matching Headings question format
    list_of_headings_match = re.search(r'List of Headings\s*\n', full_text, re.IGNORECASE)
    if list_of_headings_match:
        # After "List of Headings", skip the roman numeral headings to find passage title
        search_start = list_of_headings_match.end()
        remaining_text = full_text[search_start:]
        lines = remaining_text.split('\n')
        
        # Skip lines that are roman numerals and their associated heading texts
        # Two patterns: 
        # 1. "i" on one line, "heading text" on next line
        # 2. "i    heading text" on same line
        passage_start_line = -1
        in_heading_list = True
        last_line_was_standalone_roman = False
        
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            
            # Check if this is a standalone roman numeral (just the numeral, minimal text)
            standalone_roman_match = re.match(r'^(i{1,3}|iv|v|vi{0,3}|ix|x|xi{1,3})\s*$', stripped, re.IGNORECASE)
            if standalone_roman_match:
                # This is a standalone roman numeral, next line will be its heading text
                last_line_was_standalone_roman = True
                continue
            
            # Check if this line has roman numeral with text on same line
            roman_with_text_match = re.match(r'^(i{1,3}|iv|v|vi{0,3}|ix|x|xi{1,3})\s+(.+)$', stripped, re.IGNORECASE)
            if roman_with_text_match:
                # This is a heading with roman numeral and text on same line
                last_line_was_standalone_roman = False
                continue
            
            # If the last line was a standalone roman numeral, this line is the heading text
            if last_line_was_standalone_roman:
                last_line_was_standalone_roman = False
                continue
            
            # If we reach here and still in heading list, check if this looks like a passage title
            if in_heading_list:
                # A passage title is typically:
                # - Short (20-80 chars) and capitalized
                # - NOT a single letter (A, B, C, etc.)
                # - NOT starting with a number (like "34" for next question)
                if (20 <= len(stripped) <= 80 and 
                    stripped not in ['A', 'B', 'C', 'D', 'E', 'F', 'G'] and
                    not re.match(r'^\d+', stripped)):
                    # This is likely the passage title
                    passage_start_line = idx
                    in_heading_list = False
                    break
        
        if passage_start_line >= 0:
            # Calculate absolute position
            passage_start_pos = search_start + sum(len(lines[i]) + 1 for i in range(passage_start_line))
            
            # Find where questions resume after the passage
            # Look for "Questions \d+" after the passage start
            passage_text = full_text[passage_start_pos:]
            next_questions_match = re.search(r'\n\s*Questions?\s+\d+', passage_text, re.IGNORECASE)
            
            if next_questions_match:
                # Passage ends where next questions section starts
                passage_end_pos = passage_start_pos + next_questions_match.start()
                passage = full_text[passage_start_pos:passage_end_pos]
                # Questions are before passage + after passage
                questions_before = full_text[:passage_start_pos]
                questions_after = full_text[passage_end_pos:]
                questions = questions_before + '\n\n' + questions_after
            else:
                # No more questions after passage
                passage = full_text[passage_start_pos:]
                questions = full_text[:passage_start_pos]
            
            return passage.strip(), questions.strip()

    # Check for "READING PASSAGE" header format - common in IELTS materials
    # Pattern: "READING PASSAGE X" -> title -> content -> "Questions"
    reading_passage_match = re.search(r'READING\s+PASSAGE\s+\d+', full_text, re.IGNORECASE)
    if reading_passage_match:
        # Start looking after the "READING PASSAGE" header
        search_start = reading_passage_match.end()
        
        # Find the first "Questions \d+" after the header
        first_questions_match = re.search(r'\n\s*Questions?\s+\d+', full_text[search_start:], re.IGNORECASE)
        
        if first_questions_match:
            # The passage is from after the header to before the first questions
            passage_end_pos = search_start + first_questions_match.start()
            passage = full_text[search_start:passage_end_pos]
            questions = full_text[passage_end_pos:]
            return passage.strip(), questions.strip()

    # Standard pattern: look for "below" keyword
    passage_start = re.search(r'below\.', full_text, re.IGNORECASE)
    if passage_start:
        passage_start_index = passage_start.end()
        question_keywords = [
            'Choose the correct letter',
            'Complete the sentences',
            'Complete the summary',
            'Do the following statements agree',
            'Matching',
            r'Questions?\s+\d+'
        ]
        question_start_index = -1
        for keyword in question_keywords:
            search_result = re.search(keyword, full_text[passage_start_index:], re.IGNORECASE)
            if search_result:
                absolute_index = passage_start_index + search_result.start()
                if question_start_index == -1 or absolute_index < question_start_index:
                    question_start_index = absolute_index
        if question_start_index != -1:
            passage = full_text[passage_start_index:question_start_index]
            questions = full_text[question_start_index:]
        else:
            passage = full_text[passage_start_index:]
            questions = full_text[passage_start_index:]
    else:
        passage = full_text
        questions = full_text

    return passage.strip(), questions.strip()


def normalize_whitespace(value: str) -> str:
    return re.sub(r'\s+', ' ', value or '').strip()


def collect_passage_blocks(passage: str, blocks: Optional[List[Dict[str, Any]]]) -> List[str]:
    if not passage or not blocks:
        return []

    normalized_passage = normalize_whitespace(passage)
    if not normalized_passage:
        return []

    cursor = 0
    passage_blocks: List[str] = []

    question_prefixes = (
        'questions ',
        'choose the correct letter',
        'complete the summary',
        'complete the sentences',
        'do the following statements',
        'list of headings',
        'match the',
        'writing no more than'
    )

    for block in blocks:
        raw_text = block.get('text', '')
        normalized_block = normalize_whitespace(raw_text)
        if not normalized_block:
            continue

        lowered = normalized_block.lower()
        if lowered.startswith(question_prefixes):
            continue

        index = normalized_passage.find(normalized_block, cursor)
        if index == -1:
            continue

        passage_blocks.append(raw_text.strip())
        cursor = index + len(normalized_block)
        if cursor >= len(normalized_passage):
            break

    return passage_blocks


def collect_question_blocks(question_text: str, blocks: Optional[List[Dict[str, Any]]]) -> List[str]:
    if not question_text or not blocks:
        return []

    normalized_questions = normalize_whitespace(question_text)
    if not normalized_questions:
        return []

    cursor = 0
    question_blocks: List[str] = []

    for block in blocks:
        raw_text = block.get('text', '')
        normalized_block = normalize_whitespace(raw_text)
        if not normalized_block:
            continue

        idx = normalized_questions.find(normalized_block, cursor)
        if idx == -1:
            continue

        question_blocks.append(raw_text.strip())
        cursor = idx + len(normalized_block)
        if cursor >= len(normalized_questions):
            break

    return question_blocks


def structure_passage(raw_passage: str, passage_blocks: Optional[List[str]] = None) -> Dict[str, Any]:
    """Derive title and paragraph lettering from the reading passage."""

    def index_to_label(idx: int) -> str:
        label = ''
        current = idx
        while current >= 0:
            current, remainder = divmod(current, 26)
            label = chr(65 + remainder) + label
            current -= 1
        return label

    raw_lines = [line.rstrip('\r') for line in raw_passage.splitlines()]

    def is_instruction_line(value: str) -> bool:
        lowered = value.lower()
        if lowered.startswith('reading passage'):
            return True
        if lowered.startswith('you should spend'):
            return True
        if lowered.startswith('questions '):
            return True
        if lowered.startswith('question '):
            return True
        return False

    def is_probable_title(value: str) -> bool:
        if not value:
            return False
        stripped = value.strip()
        if not stripped or is_instruction_line(stripped):
            return False
        if re.match(r'^[A-Z]$', stripped):
            return False
        if len(stripped) > 120:
            return False
        if stripped[-1] in '.!?':
            return False
        words = stripped.split()
        if len(words) > 14:
            return False
        return True

    non_empty_lines = [line.strip() for line in raw_lines if line.strip()]
    title = ''
    for candidate in non_empty_lines[:8]:
        normalized_candidate = normalize_whitespace(candidate)
        if is_probable_title(normalized_candidate):
            title = normalized_candidate
            break

    if not title:
        for candidate in non_empty_lines:
            normalized_candidate = normalize_whitespace(candidate)
            if not is_instruction_line(normalized_candidate):
                title = normalized_candidate
                break

    if not title and non_empty_lines:
        title = normalize_whitespace(non_empty_lines[0])

    normalized_title = normalize_whitespace(title).lower()
    paragraphs: List[Dict[str, str]] = []
    intro_text = ''

    source_blocks = passage_blocks[:] if passage_blocks else []
    source_blocks = [normalize_whitespace(block) for block in source_blocks if normalize_whitespace(block)]

    def extract_letter_sections() -> Tuple[List[str], List[Tuple[str, str]]]:
        pre_letter_lines: List[str] = []
        sections: List[Tuple[str, List[str]]] = []
        current_letter: Optional[str] = None
        buffer: List[str] = []
        encountered_letter = False

        letter_only_pattern = re.compile(r'^[A-Z]$')
        inline_letter_pattern = re.compile(r'^(?P<letter>[A-Z])(?:[\.\)]\s*|\s+)(?P<body>.+)$')

        def first_alpha_is_upper(text_value: str) -> bool:
            for char in text_value:
                if char.isalpha():
                    return char.isupper()
            return False

        def flush() -> None:
            nonlocal current_letter, buffer
            if current_letter and buffer:
                sections.append((current_letter, buffer[:]))
            current_letter = None
            buffer = []

        total_lines = len(raw_lines)
        for idx, raw_line in enumerate(raw_lines):
            stripped = raw_line.strip()
            if not stripped:
                if current_letter and buffer:
                    buffer.append('')
                continue

            inline_match = inline_letter_pattern.match(stripped)
            if inline_match:
                letter = inline_match.group('letter')
                body = inline_match.group('body').strip()

                if current_letter and letter == current_letter and not first_alpha_is_upper(body):
                    buffer.append(stripped)
                    continue

                if first_alpha_is_upper(body):
                    flush()
                    current_letter = letter
                    encountered_letter = True
                    if body:
                        buffer.append(body)
                    continue

                if current_letter:
                    buffer.append(stripped)
                else:
                    pre_letter_lines.append(stripped)
                continue

            if letter_only_pattern.match(stripped):
                next_line_text = ''
                for look_ahead in range(idx + 1, total_lines):
                    candidate = raw_lines[look_ahead].strip()
                    if not candidate:
                        continue
                    next_line_text = candidate
                    break

                if next_line_text and first_alpha_is_upper(next_line_text):
                    flush()
                    current_letter = stripped
                    encountered_letter = True
                    continue
                else:
                    if current_letter:
                        buffer.append(stripped)
                    else:
                        pre_letter_lines.append(stripped)
                    continue

            if current_letter:
                buffer.append(stripped)
            else:
                pre_letter_lines.append(stripped)

        flush()

        normalized_sections = [
            (letter, normalize_whitespace(' '.join(lines)))
            for letter, lines in sections
            if normalize_whitespace(' '.join(lines))
        ]

        return pre_letter_lines, normalized_sections if encountered_letter else []

    pre_letter, letter_sections = extract_letter_sections()

    instruction_patterns = (
        re.compile(r'^reading passage', re.IGNORECASE),
        re.compile(r'^you should spend', re.IGNORECASE),
        re.compile(r'^questions?\b', re.IGNORECASE),
    )

    def filter_intro_lines(lines: List[str]) -> List[str]:
        filtered: List[str] = []
        for line in lines:
            normalized_line = normalize_whitespace(line)
            if not normalized_line:
                continue
            if normalized_line.lower() == normalized_title:
                continue
            if any(pattern.match(normalized_line) for pattern in instruction_patterns):
                continue
            filtered.append(normalized_line)
        return filtered

    def looks_like_intro(text_value: str) -> bool:
        if not text_value:
            return False
        if len(text_value) > 350:
            return False
        sentence_endings = re.findall(r'[.!?]', text_value)
        if len(sentence_endings) > 3:
            return False
        return True

    if letter_sections:
        if pre_letter:
            filtered_lines = filter_intro_lines(pre_letter)
            pre_text = normalize_whitespace(' '.join(filtered_lines))
            if pre_text and pre_text.lower() != normalized_title:
                first_letter = letter_sections[0][0] if letter_sections else None
                if first_letter and first_letter.isalpha():
                    prev_letter_ord = ord(first_letter) - 1
                    if prev_letter_ord >= ord('A'):
                        prev_letter = chr(prev_letter_ord)
                        letter_sections.insert(0, (prev_letter, pre_text))
                    else:
                        intro_text = pre_text
                else:
                    intro_text = pre_text
        paragraphs.extend({'letter': letter, 'text': text} for letter, text in letter_sections)
    elif source_blocks:
        source_blocks = [block for block in source_blocks if block.lower() != normalized_title]
        while source_blocks:
            candidate = source_blocks[0]
            if any(pattern.match(candidate) for pattern in instruction_patterns):
                source_blocks.pop(0)
                continue
            if looks_like_intro(candidate):
                intro_text = source_blocks.pop(0)
            break

        for block in source_blocks:
            if any(pattern.match(block) for pattern in instruction_patterns):
                continue
            paragraphs.append({'letter': '', 'text': block})
    else:
        blocks = re.split(r'(?:\r?\n){2,}', raw_passage)
        for block in blocks:
            cleaned = normalize_whitespace(block)
            if not cleaned or cleaned.lower() == normalized_title:
                continue
            if any(pattern.match(cleaned) for pattern in instruction_patterns):
                continue
            if not intro_text and looks_like_intro(cleaned):
                intro_text = cleaned
                continue
            paragraphs.append({'letter': '', 'text': cleaned})

    # Post-process: Merge standalone subheadings with following paragraphs
    # Subheadings are typically short (< 60 chars) and contain certain keywords
    
    merged_paragraphs = []
    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]
        text = para.get('text', '').strip()
        
        # Check if this looks like a standalone subheading
        is_subheading = False
        if len(text) < 60:  # Short paragraph
            text_lower = text.lower()
            for keyword in SUBHEADING_KEYWORDS:
                # Use word boundaries to avoid false matches like "reintroduction"
                # For multi-word keywords, check if the whole phrase exists
                if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                    is_subheading = True
                    break
        
        # If it's a subheading and there's a next paragraph, merge them
        if is_subheading and i + 1 < len(paragraphs):
            next_para = paragraphs[i + 1]
            next_text = next_para.get('text', '').strip()
            
            # Merge: subheading becomes a prefix to the next paragraph
            merged_text = f"{text}\n\n{next_text}"
            merged_para = {
                'letter': next_para.get('letter', ''),  # Keep the letter from next para
                'text': merged_text
            }
            merged_paragraphs.append(merged_para)
            i += 2  # Skip both paragraphs
        else:
            # Not a subheading or last paragraph, keep as is
            merged_paragraphs.append(para)
            i += 1
    
    paragraphs = merged_paragraphs

    return {
        'title': title,
        'intro': intro_text,
        'paragraphs': paragraphs,
        'raw': raw_passage
    }


def parse_single_choice(questions_text: str) -> List[Dict[str, Any]]:
    if not questions_text:
        return []

    # MCQ validation thresholds
    MIN_AVG_OPTION_LENGTH = 15  # Minimum average option length to filter word banks
    MAX_OPTION_LENGTH = 200      # Maximum option length to filter malformed matches
    
    # Instruction keywords that indicate this is not a real question
    INSTRUCTION_KEYWORDS = ['choose the correct letter', 'write the correct letter', 'boxes']

    # Improved pattern that requires the question number to be at the start of a line
    # This prevents matching numbers from instruction text like "boxes 27-32"
    # Allow optional newlines/whitespace after the question number for multi-line prompts
    # Use non-greedy matching and limit prompt length to avoid matching fill-in-the-blank questions
    # Stop at next question number OR "Questions" keyword
    # The prompt should be reasonable length (< 300 chars) to avoid consuming other questions from Y/N/NG sections
    # Require options A, B, C, D to be at line start to avoid matching words like "a service"
    pattern = re.compile(
        r'(?:^|\n)(\d+)\s+((?:(?!\nQuestions?\s+\d+).){10,300}?)\n\s*A\s+(.*?)\n\s*B\s+(.*?)\n\s*C\s+(.*?)\n\s*D\s+(.*?)(?=\n\d+\s+|\nQuestions?\s+\d+|\Z)',
        re.DOTALL | re.MULTILINE
    )

    questions: List[Dict[str, Any]] = []
    for match in pattern.finditer(questions_text):
        number = match.group(1)
        prompt = re.sub(r'\s+', ' ', match.group(2).strip())
        
        # Skip if prompt is too short (likely not a real question)
        if len(prompt) < 10:
            continue
        
        # Skip if this looks like instruction text
        if any(keyword in prompt.lower() for keyword in INSTRUCTION_KEYWORDS):
            continue
        
        # Skip if this section is from a Y/N/NG question section
        # Check if the text leading up to this question contains Y/N/NG instructions
        # Look back further (1000 chars) to catch Y/N/NG instructions that might be farther up
        section_before = questions_text[max(0, match.start()-1000):match.start()]
        section_before_upper = section_before.upper()
        if 'YES' in section_before_upper and 'NOT GIVEN' in section_before_upper:
            last_questions_idx = section_before_upper.rfind('QUESTIONS')
            if last_questions_idx != -1:
                trailing_segment = section_before_upper[last_questions_idx:]
                if ('CHOOSE THE CORRECT LETTER' not in trailing_segment and
                    'WRITE THE CORRECT LETTER' not in trailing_segment):
                    # This is likely a Y/N/NG section, skip it
                    continue
        
        # Find the last sentence of the prompt
        sentences = re.split(r'(?<=[.?!])\s+', prompt)
        actual_prompt = sentences[-1] if sentences else ''
        
        options = [re.sub(r'\s+', ' ', match.group(i).strip()) for i in range(3, 7) if match.group(i)]
        
        # Validate options - they should have reasonable length
        if not options or any(len(opt) < 3 for opt in options):
            continue
        
        # Check for YES/NO/NOT GIVEN pattern in options - if found, this is likely not an MCQ
        # Y/N/NG questions sometimes have A, B, C, D markers but the options are YES/NO/NOT GIVEN
        option_text_combined = ' '.join(options).upper()
        if ('YES' in option_text_combined and 'NOT GIVEN' in option_text_combined) or \
           (option_text_combined.count('YES') >= 2 and option_text_combined.count('NO') >= 2):
            continue
        
        # Check that options look like real options (not just single words or letters)
        # Real MCQ options typically have 10-150 characters
        # Skip if most options are very short OR if any option is extremely long
        avg_option_length = sum(len(opt) for opt in options) / len(options)
        max_option_length = max(len(opt) for opt in options)
        
        # Filter out word banks (very short options) and malformed matches (very long options)
        if avg_option_length < MIN_AVG_OPTION_LENGTH or max_option_length > MAX_OPTION_LENGTH:
            continue
        
        if options:
            questions.append({
                'type': 'single_choice',
                'number': number,
                'text': actual_prompt,
                'options': options,
                'match_start': match.start(),
                'match_end': match.end()
            })

    return questions


def parse_summary_completion(questions_text: str, blocks: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    if not blocks:
        return None

    lowered_questions = (questions_text or '').lower()
    summary_markers = (
        'complete the summary',
        'complete the notes',
        'complete the note'
    )
    if not any(marker in lowered_questions for marker in summary_markers):
        return None

    def normalize(text_value: str) -> str:
        cleaned = re.sub(r'\s+', ' ', text_value)
        replacements = (
            ('\u2019', "'"),
            ('\u2018', "'"),
            ('\u2013', '-'),
            ('\u2014', '-'),
            ('\uFFFD', '-'),
            ('\u2022', ' '),  # bullet
            ('\u25CF', ' ')
        )
        for before, after in replacements:
            cleaned = cleaned.replace(before, after)
        return cleaned.strip()

    def is_option_line(text_value: str) -> bool:
        stripped = text_value.strip()
        if not stripped:
            return False
        lowered = stripped.lower()
        if 'write the correct letter' in lowered or 'choose the correct letter' in lowered:
            return False
        return bool(re.match(r'^[A-Z](?:[).:-]|\s{2,})\s+\S', stripped))

    blank_pattern = re.compile(r'(?P<num>\d{1,2})\s*[_]{2,}')

    summary_anchor_idx: Optional[int] = None
    for idx, block in enumerate(blocks):
        plain_text = normalize(block.get('text', ''))
        if not plain_text:
            continue
        if blank_pattern.search(plain_text):
            summary_anchor_idx = idx
            break

    if summary_anchor_idx is None:
        return None

    summary_page = blocks[summary_anchor_idx].get('page_index')
    if summary_page is None:
        return None

    option_lines: List[str] = []
    option_range_start = max(0, summary_anchor_idx - 12)
    for block in blocks[option_range_start:summary_anchor_idx]:
        if block.get('page_index') != summary_page:
            continue
        plain = normalize(block.get('text', ''))
        if plain and is_option_line(plain):
            option_lines.append(plain)

    seen_option_lines = set(option_lines)

    start_idx = summary_anchor_idx
    while start_idx > 0:
        prev_block = blocks[start_idx - 1]
        if prev_block.get('page_index') != summary_page:
            break
        prev_plain = normalize(prev_block.get('text', ''))
        if not prev_plain:
            start_idx -= 1
            continue
        lowered_prev = prev_plain.lower()
        if lowered_prev.startswith('questions ') or is_option_line(prev_plain):
            break
        start_idx -= 1

    summary_lines: List[str] = []
    option_lines_after: List[str] = []
    idx = start_idx
    while idx < len(blocks):
        block = blocks[idx]
        if block.get('page_index') != summary_page:
            break
        plain = normalize(block.get('text', ''))
        if not plain:
            idx += 1
            continue
        lowered_plain = plain.lower()
        if is_option_line(plain) and idx >= summary_anchor_idx:
            if plain not in seen_option_lines:
                option_lines_after.append(plain)
                seen_option_lines.add(plain)
            idx += 1
            continue
        if idx > summary_anchor_idx and (
            lowered_plain.startswith('questions ')
            or lowered_plain.startswith('choose the correct letter')
            or lowered_plain.startswith('write the correct letter')
            or lowered_plain.startswith('list of ')
        ):
            break
        summary_lines.append(plain)
        idx += 1

    option_lines = list(set(option_lines + option_lines_after))

    if not summary_lines:
        return None

    first_blank_idx: Optional[int] = None
    for idx, line in enumerate(summary_lines):
        if blank_pattern.search(line):
            first_blank_idx = idx
            break

    if first_blank_idx is not None and first_blank_idx > 0:
        start_from = max(0, first_blank_idx - 1)
        summary_lines = summary_lines[start_from:]

    summary_text = '\n'.join(summary_lines).strip()
    if not summary_text:
        return None

    blank_numbers: List[str] = []

    def blank_replacer(match: re.Match) -> str:
        number = match.group('num')
        blank_numbers.append(number)
        return f'[{number}]'

    display_summary = blank_pattern.sub(blank_replacer, summary_text)
    blank_numbers = list(dict.fromkeys(blank_numbers))

    option_entries: List[Dict[str, str]] = []

    if not blank_numbers:
        return None

    return {
        'type': 'summary_completion',
        'text': display_summary,
        'blanks': blank_numbers,
        'options': option_entries
    }

def parse_paragraph_matching(questions_text: str) -> List[Dict[str, Any]]:
    if not questions_text:
        return []

    heading_pattern = re.compile(r'Questions?\s+(\d+)(?:\s*[-\u2013]\s*(\d+))?', re.IGNORECASE)
    matches = list(heading_pattern.finditer(questions_text))
    if not matches:
        return []

    def extract_paragraph_options(text_value: str) -> List[str]:
        if not text_value:
            return []

        normalized_text = text_value.replace('\u2013', '-').replace('\u2014', '-').replace('\u2012', '-')

        letters: List[str] = []

        for start_letter, end_letter in re.findall(r'([A-Z])\s*-[\s]*([A-Z])', normalized_text):
            start_ord = ord(start_letter)
            end_ord = ord(end_letter)
            if start_ord <= end_ord:
                letter_range = range(start_ord, end_ord + 1)
            else:
                letter_range = range(start_ord, end_ord - 1, -1)
            for code in letter_range:
                candidate = chr(code)
                if candidate not in letters:
                    letters.append(candidate)

        for token in re.findall(r'\b([A-Z])\b', normalized_text):
            if token not in letters:
                letters.append(token)

        if letters:
            return letters

        for match in re.finditer(r'(?:paragraphs?|sections?)\s+([A-Z][^.;]*)', text_value, re.IGNORECASE):
            segment = re.split(r'[.;]', match.group(1))[0]
            for token in re.split(r'[;,\s]+', segment):
                cleaned = token.strip().upper()
                if len(cleaned) == 1 and cleaned.isalpha() and cleaned not in letters:
                    letters.append(cleaned)

        return letters

    sections: List[Dict[str, Any]] = []

    for idx, heading in enumerate(matches):
        start_idx = heading.start()
        end_idx = matches[idx + 1].start() if idx + 1 < len(matches) else len(questions_text)
        section_text = questions_text[start_idx:end_idx].strip()
        if not section_text:
            continue

        lowered_section = section_text.lower()
        if not any(keyword in lowered_section for keyword in ('which paragraph', 'which section')):
            continue

        lines = section_text.splitlines()
        title = ''
        instruction_lines: List[str] = []
        statement_lines: List[str] = []
        statement_started = False

        for line in lines:
            raw_line = line.rstrip()
            stripped = raw_line.strip()
            if not stripped:
                continue
            if not title:
                title = normalize_whitespace(stripped)
                continue
            if re.match(r'\d{1,2}\s+', stripped):
                statement_started = True
            if statement_started:
                statement_lines.append(raw_line)
            else:
                instruction_lines.append(stripped)

        if not title or not statement_lines:
            continue

        statements_block = '\n'.join(statement_lines).strip()
        statement_pattern = re.compile(r'(\d{1,2})\s+(.*?)(?=(?:\n\d{1,2}\s)|\Z)', re.DOTALL)
        statements: List[Dict[str, str]] = []
        seen_numbers = set()
        for stmt_match in statement_pattern.finditer(statements_block):
            number = stmt_match.group(1)
            text_value = normalize_whitespace(stmt_match.group(2))
            
            # Skip if already seen this number (avoid duplicates from annotations)
            if number in seen_numbers:
                continue
            
            # Skip if text is too short (likely an annotation)
            if len(text_value) < 15:
                continue
            
            # Skip if text contains mostly non-ASCII characters (likely Chinese annotations)
            ascii_count = sum(1 for c in text_value if ord(c) < 128)
            if ascii_count < len(text_value) * 0.5:  # Less than 50% ASCII
                continue
            
            if text_value:
                statements.append({'number': number, 'text': text_value})
                seen_numbers.add(number)

        if not statements:
            continue

        instructions_clean = [normalize_whitespace(line) for line in instruction_lines if normalize_whitespace(line)]
        options = extract_paragraph_options(' '.join(instructions_clean))

        sections.append({
            'type': 'paragraph_matching',
            'title': title,
            'instructions': instructions_clean,
            'statements': statements,
            'options': options,
            'match_start': start_idx,
            'match_end': end_idx
        })

    return sections


def parse_yes_no_not_given(questions_text: str) -> List[Dict[str, Any]]:
    if not questions_text:
        return []

    lines = questions_text.splitlines()

    def clean(value: str) -> str:
        text_value = value.strip()
        if not text_value:
            return ''
        replacements = (
            ('\u2013', '-'),
            ('\u2014', '-'),
            ('\u2019', "'"),
            ('\u2018', "'"),
        )
        for before, after in replacements:
            text_value = text_value.replace(before, after)
        return re.sub(r'\s+', ' ', text_value)

    sections: List[Dict[str, Any]] = []
    i = 0
    total_lines = len(lines)

    while i < total_lines:
        stripped = lines[i].strip()
        heading_match = re.match(r'Questions?\s+(\d+)(?:\s*[-\u2013]\s*(\d+))?', stripped, re.IGNORECASE)
        if not heading_match:
            i += 1
            continue

        range_start_num = int(heading_match.group(1))
        range_end_num = heading_match.group(2)
        range_end_num = int(range_end_num) if range_end_num else None

        j = i + 1
        section_lines = [lines[i]]
        while j < total_lines and not re.match(r'Questions?\s+\d+', lines[j].strip(), re.IGNORECASE):
            section_lines.append(lines[j])
            j += 1

        section_upper = ' '.join(section_lines).upper()
        if ('YES' in section_upper and 'NOT GIVEN' in section_upper) or (
            'TRUE' in section_upper and 'NOT GIVEN' in section_upper
        ):
            statement_start_idx: Optional[int] = None
            for idx, line in enumerate(section_lines):
                if re.match(r'\s*\d+\s+', line):
                    statement_start_idx = idx
                    break

            if statement_start_idx is not None:
                instruction_lines = section_lines[:statement_start_idx]
                cleaned_instructions = [clean(line) for line in instruction_lines if clean(line)]

                title = cleaned_instructions[0] if cleaned_instructions else clean(section_lines[0])
                additional_instructions = cleaned_instructions[1:] if len(cleaned_instructions) > 1 else []

                statements_block = '\n'.join(section_lines[statement_start_idx:])
                # Stop at option lists (A  text, B  text) or "List of" markers
                # Split by double newline or when we hit option markers
                statements_text = statements_block.strip()
                
                # Find where options/word banks start (lines like "A  word" or "List of")
                # Fixed: Only match single letters (A, B, C) not abbreviations (C. Auguste)
                option_start = -1
                # Pattern explanation:
                # ^[A-Z] - starts with capital letter
                # (?:[):-]\s+|\s{2,}) - followed by either:
                #   [):-]\s+ - one of ), :, or - with spaces (e.g., "A) ", "B: ", "C- ")
                #   \s{2,} - OR two or more spaces (e.g., "A  ")
                # \S - followed by non-whitespace character
                # Deliberately excludes period (.) to avoid matching abbreviations like "C. Auguste"
                letter_option_pattern = re.compile(r'^[A-Z](?:[):-]\s+|\s{2,})\S')
                for line in statements_text.split('\n'):
                    stripped_line = line.strip()
                    if not stripped_line:
                        continue
                    if letter_option_pattern.match(stripped_line) or re.match(r'^List of', stripped_line, re.IGNORECASE):
                        option_start = statements_text.find(line)
                        break
                
                if option_start > 0:
                    statements_text = statements_text[:option_start].strip()
                
                statement_pattern = re.compile(r'(\d+)\s+(.*?)(?=(?:\n\s*\d+)|\Z)', re.DOTALL)
                statements: List[Dict[str, str]] = []
                for match in statement_pattern.finditer(statements_text):
                    number = match.group(1)
                    number_int = int(number)

                    if range_end_num is not None:
                        if number_int < range_start_num:
                            continue
                        if number_int > range_end_num:
                            break
                    else:
                        if number_int < range_start_num:
                            continue
                        if number_int - range_start_num > 10:
                            break

                    text_value = clean(match.group(2))
                    if text_value:
                        statements.append({'number': number, 'text': text_value})

                if statements:
                    options = ['YES', 'NO', 'NOT GIVEN'] if 'YES' in section_upper else ['TRUE', 'FALSE', 'NOT GIVEN']
                    sections.append({
                        'type': 'yes_no_not_given',
                        'title': title,
                        'instructions': additional_instructions,
                        'statements': statements,
                        'options': options
                    })

        i = j

    return sections


def parse_matching_headings(questions_text: str) -> List[Dict[str, Any]]:
    """Parse Matching Headings questions - match roman numeral headings (i, ii, iii) to paragraphs (A, B, C)."""
    if not questions_text:
        return []

    sections: List[Dict[str, Any]] = []
    heading_pattern = re.compile(r'Questions?\s+(\d+)(?:\s*[-\u2013]\s*(\d+))?', re.IGNORECASE)
    matches = list(heading_pattern.finditer(questions_text))
    
    if not matches:
        return []

    for idx, heading_match in enumerate(matches):
        start_idx = heading_match.start()
        end_idx = matches[idx + 1].start() if idx + 1 < len(matches) else len(questions_text)
        section_text = questions_text[start_idx:end_idx].strip()
        
        lowered = section_text.lower()
        if 'heading' not in lowered:
            continue
        
        lines = section_text.splitlines()
        title = ''
        instructions: List[str] = []
        headings: List[Dict[str, str]] = []
        paragraphs: List[str] = []
        
        # Parse headings with roman numerals
        heading_list_started = False
        paragraph_list_started = False
        pending_roman = None  # Track standalone roman numerals
        pending_paragraph_number: Optional[str] = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
                
            if not title:
                title = normalize_whitespace(stripped)
                continue
            
            # Check if this is a standalone roman numeral (no text after it)
            standalone_roman_match = re.match(r'^(i{1,3}|iv|v|vi{0,3}|ix|x|xi{1,3})\s*$', stripped, re.IGNORECASE)
            if standalone_roman_match:
                heading_list_started = True
                pending_roman = standalone_roman_match.group(1)
                continue
            
            # Check for heading list (i, ii, iii, iv, etc.) with text on same line
            roman_with_text_match = re.match(r'^(i{1,3}|iv|v|vi{0,3}|ix|x|xi{1,3})\s+(.+)$', stripped, re.IGNORECASE)
            if roman_with_text_match:
                heading_list_started = True
                roman = roman_with_text_match.group(1)
                text = normalize_whitespace(roman_with_text_match.group(2))
                headings.append({'key': roman, 'text': text})
                pending_roman = None
                continue
            
            # If we have a pending roman numeral and this line has text, pair them
            if pending_roman and len(stripped) > 3:
                text = normalize_whitespace(stripped)
                headings.append({'key': pending_roman, 'text': text})
                pending_roman = None
                continue
            
            # Check for paragraph list (A, B, C, etc.) - allow multiple spaces
            para_match = re.match(r'^(\d+)\s+(?:Paragraph|Section)\s+([A-Z])$', stripped, re.IGNORECASE)
            if para_match:
                paragraph_list_started = True
                number = para_match.group(1)
                letter = para_match.group(2)
                paragraphs.append({'number': number, 'letter': letter})
                pending_paragraph_number = None
                continue

            # Handle number on its own line followed by "Paragraph X"
            if re.match(r'^\d+$', stripped):
                pending_paragraph_number = stripped
                paragraph_list_started = True
                continue

            separate_para_match = re.match(r'^(?:Paragraph|Section)\s+([A-Z])$', stripped, re.IGNORECASE)
            if pending_paragraph_number and separate_para_match:
                letter = separate_para_match.group(1)
                paragraphs.append({'number': pending_paragraph_number, 'letter': letter})
                pending_paragraph_number = None
                paragraph_list_started = True
                continue
            
            # Instructions
            if not heading_list_started and not paragraph_list_started:
                instructions.append(normalize_whitespace(stripped))
        
        # If we found paragraphs but no headings, look for "List of Headings" elsewhere in the text
        if paragraphs and not headings:
            # Look for "List of Headings" in the remaining text after this section
            list_of_headings_match = re.search(r'List of Headings\s*\n', questions_text[end_idx:], re.IGNORECASE)
            if list_of_headings_match:
                # Parse headings from this section
                heading_section_start = end_idx + list_of_headings_match.end()
                # Read until next "Questions" section or end of text
                next_questions_match = re.search(r'\nQuestions?\s+\d+', questions_text[heading_section_start:], re.IGNORECASE)
                heading_section_end = heading_section_start + (next_questions_match.start() if next_questions_match else 1000)
                heading_section_text = questions_text[heading_section_start:heading_section_end]
                
                # Parse roman numerals with text
                heading_lines = heading_section_text.splitlines()
                for line in heading_lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    roman_match = re.match(r'^(i{1,3}|iv|v|vi{0,3}|ix|x|xi{1,3})\s+(.+)$', stripped, re.IGNORECASE)
                    if roman_match:
                        roman = roman_match.group(1)
                        text = normalize_whitespace(roman_match.group(2))
                        headings.append({'key': roman, 'text': text})
        
        if headings and paragraphs and title:
            sections.append({
                'type': 'matching_headings',
                'title': title,
                'instructions': instructions,
                'headings': headings,
                'paragraphs': paragraphs,
                'match_start': start_idx,
                'match_end': end_idx
            })
    
    return sections


def parse_matching_features(questions_text: str) -> List[Dict[str, Any]]:
    """Parse Matching Features questions - match statements to persons/features/entities."""
    if not questions_text:
        return []
    
    sections: List[Dict[str, Any]] = []
    heading_pattern = re.compile(r'Questions?\s+(\d+)(?:\s*[-\u2013]\s*(\d+))?', re.IGNORECASE)
    matches = list(heading_pattern.finditer(questions_text))
    
    if not matches:
        return []
    
    for idx, heading_match in enumerate(matches):
        start_idx = heading_match.start()
        end_idx = matches[idx + 1].start() if idx + 1 < len(matches) else len(questions_text)
        section_text = questions_text[start_idx:end_idx].strip()
        
        lowered = section_text.lower()
        # Look for matching features keywords - expanded to include "classify"
        if not any(keyword in lowered for keyword in ['match', 'list of', 'classify']):
            continue
        
        # Avoid confusion with paragraph matching
        if 'which paragraph' in lowered:
            continue
            
        lines = section_text.splitlines()
        title = ''
        instructions: List[str] = []
        features: List[Dict[str, str]] = []
        statements: List[Dict[str, str]] = []

        feature_list_started = False
        statement_list_started = False
        in_list_section = False
        pending_feature_letter: Optional[str] = None
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            if not title:
                title = normalize_whitespace(stripped)
                continue
            
            # Check for "List of" header (for reversed order where statements come first)
            if re.match(r'^List of ', stripped, re.IGNORECASE):
                in_list_section = True
                continue
            
            # Check for numbered statements (can appear first in some formats)
            statement_match = re.match(r'^(\d+)\s+(.+)$', stripped)
            if statement_match and not in_list_section:
                statement_list_started = True
                number = statement_match.group(1)
                text = normalize_whitespace(statement_match.group(2))
                statements.append({'number': number, 'text': text})
                continue
            
            # Check for feature list (A Name1, B Name2, etc.)
            feature_match = re.match(r'^([A-Z])\s+(.+)$', stripped)
            if feature_match:
                letter = feature_match.group(1)
                name = normalize_whitespace(feature_match.group(2))
                if len(letter) == 1 and not re.match(r'^\d+', name):
                    feature_list_started = True
                    features.append({'key': letter, 'text': name})
                    pending_feature_letter = None
                    continue

            if re.match(r'^[A-Z]$', stripped):
                pending_feature_letter = stripped
                feature_list_started = True
                continue

            if pending_feature_letter and stripped:
                if not re.match(r'^Questions?\s+\d+', stripped, re.IGNORECASE):
                    name = normalize_whitespace(stripped)
                    if name and not re.match(r'^\d+', name):
                        features.append({'key': pending_feature_letter, 'text': name})
                        feature_list_started = True
                        pending_feature_letter = None
                        continue
            
            # Instructions (collect everything before statements/features start)
            if not feature_list_started and not statement_list_started:
                instructions.append(normalize_whitespace(stripped))
        
        # If we have statements but no features, look for the feature list in subsequent sections
        # This handles cases like PDF84 where the list appears after other questions
        if statements and not features and idx + 1 < len(matches):
            # Search for "List of" in the text after this section
            search_text = questions_text[end_idx:]
            list_match = re.search(r'List of [A-Za-z]+', search_text, re.IGNORECASE)
            if list_match:
                # Extract features from the list section
                list_start = end_idx + list_match.end()
                # Read until next "Questions" section or end
                next_q_match = re.search(r'\n\s*Questions?\s+\d+', search_text[list_match.end():], re.IGNORECASE)
                list_end = list_start + (next_q_match.start() if next_q_match else 500)
                list_text = questions_text[list_start:list_end]
                
                # Parse features from this section
                pending_letter = None
                for line in list_text.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    feature_match = re.match(r'^([A-Z])\s+(.+)$', stripped)
                    if feature_match:
                        letter = feature_match.group(1)
                        name = normalize_whitespace(feature_match.group(2))
                        if len(letter) == 1 and not re.match(r'^\d+', name):
                            features.append({'key': letter, 'text': name})
                            pending_letter = None
                        continue
                    if re.match(r'^[A-Z]$', stripped):
                        pending_letter = stripped
                        continue
                    if pending_letter:
                        name = normalize_whitespace(stripped)
                        if name and not re.match(r'^\d+', name):
                            features.append({'key': pending_letter, 'text': name})
                            pending_letter = None
        
        if features and statements and title:
            sections.append({
                'type': 'matching_features',
                'title': title,
                'instructions': instructions,
                'features': features,
                'statements': statements,
                'match_start': start_idx,
                'match_end': end_idx
            })
    
    return sections


def parse_matching_sentence_endings(questions_text: str) -> List[Dict[str, Any]]:
    """Parse Matching Sentence Endings questions - complete sentences by matching beginnings to endings."""
    if not questions_text:
        return []
    
    sections: List[Dict[str, Any]] = []
    heading_pattern = re.compile(r'Questions?\s+(\d+)(?:\s*[-\u2013]\s*(\d+))?', re.IGNORECASE)
    matches = list(heading_pattern.finditer(questions_text))
    
    if not matches:
        return []
    
    for idx, heading_match in enumerate(matches):
        start_idx = heading_match.start()
        end_idx = matches[idx + 1].start() if idx + 1 < len(matches) else len(questions_text)
        section_text = questions_text[start_idx:end_idx].strip()
        
        lowered = section_text.lower()
        
        # Exclude Yes/No/Not Given and True/False/Not Given sections
        if ('yes' in lowered and 'not given' in lowered) or ('true' in lowered and 'not given' in lowered):
            continue
        
        # Exclude MCQ sections
        if 'choose the correct letter' in lowered or 'write the correct letter' in lowered:
            continue
        
        # Look for sentence ending keywords
        if not any(keyword in lowered for keyword in ['complete', 'sentence', 'ending']):
            continue
        
        lines = section_text.splitlines()
        title = ''
        instructions: List[str] = []
        sentence_beginnings: List[Dict[str, str]] = []
        endings: List[Dict[str, str]] = []
        
        beginnings_started = False
        endings_started = False
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            if not title:
                title = normalize_whitespace(stripped)
                continue
            
            # Check for sentence beginnings (numbered)
            beginning_match = re.match(r'^(\d+)\s+(.+)$', stripped)
            if beginning_match and not endings_started:
                beginnings_started = True
                number = beginning_match.group(1)
                text = normalize_whitespace(beginning_match.group(2))
                sentence_beginnings.append({'number': number, 'text': text})
                continue
            
            # Check for endings (lettered)
            ending_match = re.match(r'^([A-Z])\s+(.+)$', stripped)
            if ending_match and beginnings_started:
                endings_started = True
                letter = ending_match.group(1)
                text = normalize_whitespace(ending_match.group(2))
                if len(letter) == 1:
                    endings.append({'key': letter, 'text': text})
                    continue
            
            # Instructions
            if not beginnings_started:
                instructions.append(normalize_whitespace(stripped))
        
        if sentence_beginnings and endings and title:
            sections.append({
                'type': 'matching_sentence_endings',
                'title': title,
                'instructions': instructions,
                'sentence_beginnings': sentence_beginnings,
                'endings': endings,
                'match_start': start_idx,
                'match_end': end_idx
            })
    
    return sections


def parse_diagram_label_completion(questions_text: str) -> List[Dict[str, Any]]:
    """Parse Diagram Label Completion questions - label diagram with words from passage."""
    if not questions_text:
        return []
    
    sections: List[Dict[str, Any]] = []
    heading_pattern = re.compile(r'Questions?\s+(\d+)(?:\s*[-\u2013]\s*(\d+))?', re.IGNORECASE)
    matches = list(heading_pattern.finditer(questions_text))
    
    if not matches:
        return []
    
    for idx, heading_match in enumerate(matches):
        start_idx = heading_match.start()
        end_idx = matches[idx + 1].start() if idx + 1 < len(matches) else len(questions_text)
        section_text = questions_text[start_idx:end_idx].strip()
        
        lowered = section_text.lower()
        # Look for diagram/label keywords
        if not any(keyword in lowered for keyword in ['diagram', 'label', 'figure', 'illustration']):
            continue
        
        lines = section_text.splitlines()
        title = ''
        instructions: List[str] = []
        labels: List[Dict[str, str]] = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            if not title:
                title = normalize_whitespace(stripped)
                continue
            
            # Check for label items (numbered)
            label_match = re.match(r'^(\d+)\s+(.+)$', stripped)
            if label_match:
                number = label_match.group(1)
                text = normalize_whitespace(label_match.group(2))
                # Check if it's a blank to fill
                if '_' in text or 'label' in text.lower():
                    labels.append({'number': number, 'text': text})
                    continue
            
            # Instructions
            if not labels:
                instructions.append(normalize_whitespace(stripped))
        
        if labels and title:
            sections.append({
                'type': 'diagram_label_completion',
                'title': title,
                'instructions': instructions,
                'labels': labels,
                'match_start': start_idx,
                'match_end': end_idx
            })
    
    return sections


def parse_short_answer_questions(questions_text: str) -> List[Dict[str, Any]]:
    """Parse Short-Answer Questions - answer using NO MORE THAN X WORDS."""
    if not questions_text:
        return []
    
    questions: List[Dict[str, Any]] = []
    
    # Look for the "NO MORE THAN X WORDS" pattern
    word_limit_pattern = re.compile(
        r'(?:using|write|answer)?\s*(?:no more than|maximum of|maximum)\s+(\w+)\s+(?:words?|numbers?)',
        re.IGNORECASE
    )
    
    # Only proceed if we find word limit instructions
    if not word_limit_pattern.search(questions_text):
        return []
    
    # Extract word limit
    word_limit_match = word_limit_pattern.search(questions_text)
    word_limit = word_limit_match.group(1) if word_limit_match else 'THREE'
    
    # Find the section that contains short answer questions
    heading_pattern = re.compile(r'Questions?\s+(\d+)(?:\s*[-\u2013]\s*(\d+))?', re.IGNORECASE)
    matches = list(heading_pattern.finditer(questions_text))
    
    if not matches:
        return []
    
    instruction_markers = (
        'answer the questions',
        'choose no more than',
        'write your answers',
        'using no more than',
        'use no more than',
        'reading passage'
    )

    for idx, heading_match in enumerate(matches):
        start_idx = heading_match.start()
        end_idx = matches[idx + 1].start() if idx + 1 < len(matches) else len(questions_text)
        section_text = questions_text[start_idx:end_idx].strip()

        # Check if this section has word limit instructions
        if not word_limit_pattern.search(section_text):
            continue

        question_number_pattern = re.compile(r'(?m)^(?P<number>\d{1,2})\s*(?:[).:-])?')
        number_matches = list(question_number_pattern.finditer(section_text))

        for q_idx, match in enumerate(number_matches):
            number = match.group('number')
            content_start = match.end()
            content_end = number_matches[q_idx + 1].start() if q_idx + 1 < len(number_matches) else len(section_text)
            raw_chunk = section_text[content_start:content_end]

            # Break chunk into lines and filter out instructional text
            chunk_lines = []
            for line in raw_chunk.splitlines():
                cleaned_line = normalize_whitespace(line)
                if not cleaned_line:
                    continue
                lowered_line = cleaned_line.lower()
                if any(marker in lowered_line for marker in instruction_markers):
                    continue
                chunk_lines.append(cleaned_line)

            text = normalize_whitespace(' '.join(chunk_lines))

            if not text:
                continue

            questions.append({
                'type': 'short_answer',
                'number': number,
                'text': text,
                'word_limit': word_limit,
                'match_start': match.start('number') + start_idx,
                'match_end': content_end + start_idx
            })
    
    return questions


def parse_questions(questions_text: str, blocks: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    consumed_numbers: set[str] = set()
    consumed_ranges: List[Tuple[int, int]] = []
    question_blocks = collect_question_blocks(questions_text, blocks)

    def parse_number(value: Any) -> Optional[int]:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                return int(stripped)
        return None

    def collect_section_numbers(entry: Dict[str, Any]) -> List[int]:
        numbers: List[int] = []

        def add(value: Any) -> None:
            number = parse_number(value)
            if number is not None:
                numbers.append(number)

        add(entry.get('number'))

        for blank in entry.get('blanks', []):
            add(blank)

        nested_keys = (
            'statements',
            'paragraphs',
            'sentence_beginnings',
            'labels',
            'questions'
        )

        for key in nested_keys:
            items = entry.get(key, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    add(item.get('number'))
                else:
                    add(item)

        return numbers

    def is_consumed(start: int, end: int) -> bool:
        if start < 0 or end < 0:
            return False
        for r_start, r_end in consumed_ranges:
            if max(start, r_start) < min(end, r_end):
                return True
        return False

    # Parse summary completion (has blanks with word bank)
    summary = parse_summary_completion(questions_text, blocks)
    if summary:
        questions.append(summary)
        consumed_numbers.update(summary['blanks'])

    # Parse matching headings (roman numerals to paragraphs)
    matching_heading_sections = parse_matching_headings(questions_text)
    for section in matching_heading_sections:
        start = section.get('match_start', -1)
        end = section.get('match_end', -1)
        if is_consumed(start, end):
            continue
        if section.get('paragraphs'):
            section_numbers = {p['number'] for p in section['paragraphs']}
            if section_numbers & consumed_numbers:
                continue
            consumed_numbers.update(section_numbers)
        questions.append(section)
        if start >= 0 and end >= 0:
            consumed_ranges.append((start, end))

    # Parse paragraph matching (which paragraph contains information)
    paragraph_sections = parse_paragraph_matching(questions_text)
    for section in paragraph_sections:
        start = section.get('match_start', -1)
        end = section.get('match_end', -1)
        if is_consumed(start, end):
            continue
        section_numbers = {statement['number'] for statement in section['statements']}
        if section_numbers & consumed_numbers:
            continue
        questions.append(section)
        consumed_numbers.update(section_numbers)
        if start >= 0 and end >= 0:
            consumed_ranges.append((start, end))

    # Parse matching features (match statements to persons/features)
    matching_feature_sections = parse_matching_features(questions_text)
    for section in matching_feature_sections:
        start = section.get('match_start', -1)
        end = section.get('match_end', -1)
        if is_consumed(start, end):
            continue
        section_numbers = {statement['number'] for statement in section['statements']}
        if section_numbers & consumed_numbers:
            continue
        questions.append(section)
        consumed_numbers.update(section_numbers)
        if start >= 0 and end >= 0:
            consumed_ranges.append((start, end))

    # Parse matching sentence endings
    sentence_ending_sections = parse_matching_sentence_endings(questions_text)
    for section in sentence_ending_sections:
        start = section.get('match_start', -1)
        end = section.get('match_end', -1)
        if is_consumed(start, end):
            continue
        section_numbers = {sb['number'] for sb in section['sentence_beginnings']}
        if section_numbers & consumed_numbers:
            continue
        questions.append(section)
        consumed_numbers.update(section_numbers)
        if start >= 0 and end >= 0:
            consumed_ranges.append((start, end))

    # Parse diagram label completion
    diagram_sections = parse_diagram_label_completion(questions_text)
    for section in diagram_sections:
        start = section.get('match_start', -1)
        end = section.get('match_end', -1)
        if is_consumed(start, end):
            continue
        section_numbers = {label['number'] for label in section['labels']}
        if section_numbers & consumed_numbers:
            continue
        questions.append(section)
        consumed_numbers.update(section_numbers)
        if start >= 0 and end >= 0:
            consumed_ranges.append((start, end))

    # Parse short answer questions
    short_answer_qs = parse_short_answer_questions(questions_text)
    for q in short_answer_qs:
        start = q.get('match_start', -1)
        end = q.get('match_end', -1)
        if q['number'] in consumed_numbers or is_consumed(start, end):
            continue
        questions.append(q)
        consumed_numbers.add(q['number'])
        if start >= 0 and end >= 0:
            consumed_ranges.append((start, end))

    # Parse fill-in-the-blank (Complete the sentences / Complete the summary style)
    def parse_fill_in_blanks(text: str, block_texts: List[str]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if not text:
            return results

        candidate_blocks: List[str] = []
        lowered_phrases = ('complete the summary', 'complete the sentences')

        if block_texts:
            found_header = False
            for block_text in block_texts:
                normalized_block = normalize_whitespace(block_text)
                if not normalized_block:
                    continue
                lowered = normalized_block.lower()
                if not found_header and any(phrase in lowered for phrase in lowered_phrases):
                    found_header = True

                if not found_header:
                    continue

                candidate_blocks.append(block_text)

                if re.search(r'questions?\s+\d+', lowered, re.IGNORECASE):
                    break

        segment_text = '\n'.join(candidate_blocks) if candidate_blocks else text
        segment_text = re.split(r'Questions?\s+\d+', segment_text, maxsplit=1, flags=re.IGNORECASE)[0]

        pattern = re.compile(
            r'(?P<num>\d{1,2})\s*(?:[).:-])?\s*(?P<blank>_{2,})(?P<after>[^0-9_]{0,200})',
            re.DOTALL
        )

        instruction_markers = (
            'complete the summary',
            'complete the sentences',
            'write your answers'
        )

        def strip_instruction_text(value: str) -> str:
            lowered = value.lower()
            for marker in instruction_markers:
                idx = lowered.rfind(marker)
                if idx != -1:
                    value = value[idx + len(marker):]
                    lowered = value.lower()
            return value.strip()

        seen_numbers: set[str] = set()

        for match in pattern.finditer(segment_text):
            num = match.group('num')
            if num in seen_numbers:
                continue
            start_idx = match.start('num')

            prefix_chunk = segment_text[max(0, start_idx - 200):start_idx]
            prefix_clean = re.sub(r'_+', ' ', prefix_chunk)
            prefix_clean = normalize_whitespace(prefix_clean)
            prefix_clean = strip_instruction_text(prefix_clean)
            prefix_words = prefix_clean.split()
            prefix = ' '.join(prefix_words[-8:])
            if prefix:
                prefix = re.sub(r'\b\d{1,2}\b', '', prefix)
                prefix = re.split(r'[.;!?]', prefix)[-1].strip()
                prefix = normalize_whitespace(prefix)

            suffix_raw = match.group('after') or ''
            suffix_raw_stripped = suffix_raw.lstrip()
            post_blank_punct = ''
            if suffix_raw_stripped and suffix_raw_stripped[0] in '.;,!?':
                post_blank_punct = suffix_raw_stripped[0]
                suffix_raw_stripped = suffix_raw_stripped[1:]

            suffix_clean = re.sub(r'_+', ' ', suffix_raw_stripped)
            suffix_clean = normalize_whitespace(suffix_clean)
            suffix_clean = strip_instruction_text(suffix_clean)
            suffix_words = suffix_clean.split()
            suffix = ' '.join(suffix_words[:8])
            if suffix:
                suffix = re.sub(r'\b\d{1,2}\b', '', suffix)
                suffix = re.split(r'[.;!?]', suffix)[0].strip()
                suffix = normalize_whitespace(suffix)

            snippet_parts: List[str] = []
            if prefix:
                snippet_parts.append(prefix)

            blank_repr = '____'
            if post_blank_punct:
                blank_repr = f'____{post_blank_punct}'
            snippet_parts.append(blank_repr)

            append_suffix = bool(suffix)
            if append_suffix and post_blank_punct and suffix and suffix[0].isalpha() and suffix[0].isupper():
                append_suffix = False

            if append_suffix:
                snippet_parts.append(suffix)

            snippet = ' '.join(snippet_parts).strip()
            snippet = snippet.strip('-:;,')

            lowered_snippet = snippet.lower()
            if not snippet or 'write your answers' in lowered_snippet or 'complete the summary' in lowered_snippet:
                continue

            results.append({'type': 'fill_blank', 'number': num, 'text': snippet, 'match_start': match.start(), 'match_end': match.end()})
            seen_numbers.add(num)

        if results:
            return results

        # Fallback: basic chunking if underscore matching fails
        number_matches = list(re.finditer(r'\b(\d{1,2})\b', segment_text))
        for idx, nm in enumerate(number_matches):
            num = nm.group(1)
            if num in seen_numbers:
                continue

            start = nm.end()
            end = number_matches[idx + 1].start() if idx + 1 < len(number_matches) else len(segment_text)
            chunk = segment_text[start:end]
            if '_' not in chunk:
                continue

            cleaned = normalize_whitespace(chunk)
            if not cleaned:
                continue

            results.append({'type': 'fill_blank', 'number': num, 'text': cleaned, 'match_start': nm.start(), 'match_end': end})
            seen_numbers.add(num)

        return results

    fills = parse_fill_in_blanks(questions_text, question_blocks)
    for f in fills:
        start = f.get('match_start', -1)
        end = f.get('match_end', -1)
        if f['number'] in consumed_numbers or is_consumed(start, end):
            continue
        questions.append(f)
        consumed_numbers.add(f['number'])
        if start >= 0 and end >= 0:
            consumed_ranges.append((start, end))

    yes_no_sections = parse_yes_no_not_given(questions_text)
    for section in yes_no_sections:
        # This parser is section-based, so we assume it doesn't overlap badly
        questions.append(section)
        consumed_numbers.update(statement['number'] for statement in section['statements'])

    for single in parse_single_choice(questions_text):
        start = single.get('match_start', -1)
        end = single.get('match_end', -1)
        if single['number'] in consumed_numbers or is_consumed(start, end):
            continue
        questions.append(single)
        if start >= 0 and end >= 0:
            consumed_ranges.append((start, end))

    if questions:
        ordered: List[Tuple[float, float, int, Dict[str, Any]]] = []
        for idx, question in enumerate(questions):
            section_numbers = collect_section_numbers(question)
            first_number: Optional[int] = min(section_numbers) if section_numbers else None
            positional_hint = question.get('match_start')
            if not isinstance(positional_hint, int):
                positional_hint = float('inf')
            ordered.append((
                float(first_number) if first_number is not None else float('inf'),
                float(positional_hint),
                idx,
                question
            ))

        ordered.sort(key=lambda item: (item[0], item[1], item[2]))
        questions = [entry[3] for entry in ordered]

    # Clean up temporary keys from question dicts
    for q in questions:
        q.pop('match_start', None)
        q.pop('match_end', None)

    return questions


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('index'))

    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('index'))

    if not allowed_file(file.filename):
        flash('Allowed file types are pdf')
        return redirect(url_for('index'))

    upload_folder = Path(app.config['UPLOAD_FOLDER'])
    upload_folder.mkdir(parents=True, exist_ok=True)

    filename = secure_filename(file.filename)
    filepath = upload_folder / filename
    file.save(filepath)

    full_text, blocks = extract_text_and_blocks(filepath)
    passage, question_text = split_passage_questions(full_text)
    passage_blocks = collect_passage_blocks(passage, blocks)
    structured_passage = structure_passage(passage, passage_blocks)
    parsed_questions = parse_questions(question_text, blocks)

    flash('File successfully uploaded')
    return render_template('passage.html', passage=structured_passage, questions=parsed_questions)


if __name__ == '__main__':
    app.run(debug=True)
