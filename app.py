import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from flask import Flask, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

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
        
        # Skip lines that are roman numerals or their descriptions until we find the passage title
        passage_start_line = -1
        last_roman_idx = -1
        
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            
            # Check if this is a standalone roman numeral OR starts with one
            is_roman_numeral = re.match(r'^(i{1,3}|iv|v|vi{0,3}|ix|x|xi{0,3})$', stripped, re.IGNORECASE)
            starts_with_roman = re.match(r'^(i{1,3}|iv|v|vi{0,3}|ix|x|xi{0,3})\s+', stripped, re.IGNORECASE)
            
            if is_roman_numeral or starts_with_roman:
                last_roman_idx = idx
                continue
            
            # After we've seen roman numerals, look for the passage title
            # Title characteristics: short line (< 80 chars), appears after roman numerals, before paragraph letter "A"
            if last_roman_idx >= 0 and idx > last_roman_idx:
                # This line comes after roman numerals
                # If it's relatively short and not a single letter, it's likely the title
                if len(stripped) > 3 and len(stripped) < 80 and stripped != 'A':
                    passage_start_line = idx
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

    non_empty_lines = [line.strip() for line in raw_passage.splitlines() if line.strip()]
    title = non_empty_lines[0] if non_empty_lines else ''

    normalized_title = normalize_whitespace(title).lower()
    paragraphs: List[Dict[str, str]] = []
    intro_text = ''

    source_blocks = passage_blocks[:] if passage_blocks else []
    source_blocks = [normalize_whitespace(block) for block in source_blocks if normalize_whitespace(block)]

    def extract_letter_sections() -> Tuple[List[str], List[Tuple[str, str]]]:
        raw_lines = [line.rstrip('\r') for line in raw_passage.splitlines()]
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

    if letter_sections:
        if not intro_text and pre_letter:
            intro_text = normalize_whitespace(' '.join(pre_letter))
        paragraphs.extend({'letter': letter, 'text': text} for letter, text in letter_sections)
    elif source_blocks:
        source_blocks = [block for block in source_blocks if block.lower() != normalized_title]
        if source_blocks and len(source_blocks[0]) <= 120 and '.' not in source_blocks[0]:
            intro_text = source_blocks.pop(0)

        # Merge subheadings with following paragraphs
        def is_subheading(block: str, next_block: Optional[str] = None) -> bool:
            """
            Detect if a block is a subheading that should be merged with the next block.
            
            A subheading is identified by:
            1. Short length (< 50 characters)
            2. No period at the end (headings don't end with periods)
            3. Starts with capital letter
            4. Next block is significantly longer (3x threshold indicates this is a heading for that content)
            5. Matches common subheading patterns found in academic texts
            
            Args:
                block: The text block to check
                next_block: The following text block (if any)
            
            Returns:
                True if the block is likely a subheading
            """
            if not block:
                return False
            
            # Subheadings are typically short
            # Using 50 char threshold based on common academic heading lengths
            if len(block) >= 50:
                return False
            
            # Subheadings don't end with periods
            if block.endswith('.'):
                return False
            
            # Must start with capital letter
            if not block or not block[0].isupper():
                return False
            
            # If there's a next block and it's much longer (3x), this is likely a subheading
            # The 3x multiplier ensures the next block is substantial content, not another heading
            if next_block and len(next_block) > len(block) * 3:
                return True
            
            # Common subheading patterns found in academic/IELTS texts
            subheading_patterns = [
                'description of',
                'methodological',
                'lessons to',
                'conclusion',
                'introduction',
                'background',
                'discussion',
                'results',
                'methods',
                'analysis',
                'overview',
                'summary',
            ]
            
            block_lower = block.lower()
            if any(pattern in block_lower for pattern in subheading_patterns):
                return True
            
            return False
        
        i = 0
        while i < len(source_blocks):
            block = source_blocks[i]
            next_block = source_blocks[i + 1] if i + 1 < len(source_blocks) else None
            
            if is_subheading(block, next_block) and next_block:
                # Merge subheading with next paragraph
                merged_text = f"{block}. {next_block}"
                paragraphs.append({'letter': '', 'text': merged_text})
                i += 2  # Skip both blocks
            else:
                paragraphs.append({'letter': '', 'text': block})
                i += 1
    else:
        blocks = re.split(r'(?:\r?\n){2,}', raw_passage)
        for block in blocks:
            cleaned = normalize_whitespace(block)
            if not cleaned or cleaned.lower() == normalized_title:
                continue
            if not intro_text and len(cleaned) <= 120 and '.' not in cleaned:
                intro_text = cleaned
                continue
            paragraphs.append({'letter': '', 'text': cleaned})

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
    # Stop at next question number OR "Questions" keyword
    pattern = re.compile(
        r'(?:^|\n)(\d+)\s+(.*?)\s+A\s+(.*?)\s+B\s+(.*?)\s+C\s+(.*?)\s+D\s+(.*?)(?=\n\d+\s+|\nQuestions?\s+\d+|\Z)',
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
        
        # Find the last sentence of the prompt
        sentences = re.split(r'(?<=[.?!])\s+', prompt)
        actual_prompt = sentences[-1] if sentences else ''
        
        options = [re.sub(r'\s+', ' ', match.group(i).strip()) for i in range(3, 7) if match.group(i)]
        
        # Validate options - they should have reasonable length
        if not options or any(len(opt) < 3 for opt in options):
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

    if 'complete the summary' not in (questions_text or '').lower():
        return None

    def normalize(text_value: str) -> str:
        cleaned = re.sub(r'\s+', ' ', text_value)
        replacements = (
            ('\u2019', "'"),
            ('\u2018', "'"),
            ('\u2013', '-'),
            ('\u2014', '-'),
            ('\uFFFD', '-')
        )
        for before, after in replacements:
            cleaned = cleaned.replace(before, after)
        return cleaned.strip()

    def is_option_line(text_value: str) -> bool:
        tokens = [token.strip('.,()') for token in text_value.split() if token]
        letter_tokens = [token for token in tokens if len(token) == 1 and token.isupper()]
        return len(letter_tokens) >= 2

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
    if option_lines:
        raw_options = ' '.join(option_lines).replace('.', ' ')
        tokens = [token for token in re.split(r'\s+', raw_options) if token]
        idx = 0
        seen_letters: set[str] = set()
        while idx < len(tokens):
            token = tokens[idx].strip('.,()')
            if len(token) == 1 and token.isupper() and token not in seen_letters:
                letter = token
                idx += 1
                value_parts: List[str] = []
                while idx < len(tokens):
                    lookahead = tokens[idx].strip('.,()')
                    if len(lookahead) == 1 and lookahead.isupper():
                        break
                    value_parts.append(tokens[idx])
                    idx += 1
                option_text = ' '.join(value_parts).strip()
                if option_text:
                    option_entries.append({'key': letter, 'text': option_text})
                    seen_letters.add(letter)
            else:
                idx += 1

    if not blank_numbers or not option_entries:
        return None

    option_entries.sort(key=lambda option: option['key'])

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
                option_start = -1
                for line in statements_text.split('\n'):
                    if re.match(r'^[A-Z]\s+\w', line) or re.match(r'^List of', line, re.IGNORECASE):
                        option_start = statements_text.find(line)
                        break
                
                if option_start > 0:
                    statements_text = statements_text[:option_start].strip()
                
                statement_pattern = re.compile(r'(\d+)\s+(.*?)(?=(?:\n\d+\s)|\Z)', re.DOTALL)
                statements: List[Dict[str, str]] = []
                for match in statement_pattern.finditer(statements_text):
                    number = match.group(1)
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
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
                
            if not title:
                title = normalize_whitespace(stripped)
                continue
            
            # Check for heading list (i, ii, iii, iv, etc.)
            roman_match = re.match(r'^(i{1,3}|iv|v|vi{0,3}|ix|x)\s+(.+)$', stripped, re.IGNORECASE)
            if roman_match:
                heading_list_started = True
                roman = roman_match.group(1)
                text = normalize_whitespace(roman_match.group(2))
                headings.append({'key': roman, 'text': text})
                continue
            
            # Check for paragraph list (A, B, C, etc.) - allow multiple spaces
            para_match = re.match(r'^(\d+)\s+Paragraph\s+([A-Z])$', stripped, re.IGNORECASE)
            if para_match:
                paragraph_list_started = True
                number = para_match.group(1)
                letter = para_match.group(2)
                paragraphs.append({'number': number, 'letter': letter})
                continue
            
            # Instructions
            if not heading_list_started and not paragraph_list_started:
                instructions.append(normalize_whitespace(stripped))
        
        if headings and title:
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
                # Only single capital letters for features
                if len(letter) == 1 and not re.match(r'^\d+', name):
                    feature_list_started = True
                    features.append({'key': letter, 'text': name})
                    continue
            
            # Instructions (collect everything before statements/features start)
            if not feature_list_started and not statement_list_started:
                instructions.append(normalize_whitespace(stripped))
        
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
    
    for idx, heading_match in enumerate(matches):
        start_idx = heading_match.start()
        end_idx = matches[idx + 1].start() if idx + 1 < len(matches) else len(questions_text)
        section_text = questions_text[start_idx:end_idx].strip()
        
        # Check if this section has word limit instructions
        if not word_limit_pattern.search(section_text):
            continue
        
        # Find question numbers and text in this section
        question_pattern = re.compile(
            r'^(\d+)\s+(.+?)$',
            re.MULTILINE
        )
        
        for match in question_pattern.finditer(section_text):
            number = match.group(1)
            text = normalize_whitespace(match.group(2))
            
            # Filter out section headers and instructions
            if any(keyword in text.lower() for keyword in ['questions', 'answer the', 'write', 'using no more']):
                continue
            
            # Must be a real question (ends with ?)
            if text and '?' in text:
                questions.append({
                    'type': 'short_answer',
                    'number': number,
                    'text': text,
                    'word_limit': word_limit,
                    'match_start': match.start() + start_idx,
                    'match_end': match.end() + start_idx
                })
    
    return questions


def parse_questions(questions_text: str, blocks: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    consumed_numbers: set[str] = set()
    consumed_ranges: List[Tuple[int, int]] = []
    question_blocks = collect_question_blocks(questions_text, blocks)

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
