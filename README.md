# IELTS Reading Transformer

A web application that converts IELTS reading PDF files into interactive online tests. The application automatically recognizes different question types and presents them in a user-friendly format with the passage on the left and questions on the right.

## Features

- **PDF Upload**: Upload IELTS reading test PDFs through a simple web interface
- **Automatic Text Extraction**: Extracts text and structure from PDF using PyMuPDF
- **Smart Question Recognition**: Identifies and parses multiple question types:
  - Single/Multiple Choice Questions
  - Summary Completion (with word banks)
  - Paragraph Matching
  - True/False/Not Given
  - Yes/No/Not Given
  - Fill-in-the-Blank
- **Interactive Test Interface**: Clean, responsive two-panel layout
  - Reading passage with labeled paragraphs (A, B, C, etc.)
  - Questions with appropriate input controls
- **Passage Structure Recognition**: Automatically identifies:
  - Passage title
  - Introduction text
  - Paragraph lettering (A, B, C, etc.)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/imChenRH/IELTS-reading-transformer.git
cd IELTS-reading-transformer
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the Flask development server:
```bash
python app.py
```

2. Open your web browser and navigate to:
```
http://localhost:5000
```

3. Upload an IELTS reading PDF file using the upload form

4. The application will:
   - Extract the text from the PDF
   - Identify the reading passage
   - Recognize and parse all question types
   - Display the interactive test interface

## Project Structure

```
IELTS-reading-transformer/
├── app.py              # Main Flask application with PDF processing logic
├── templates/
│   ├── index.html      # Upload page
│   └── passage.html    # Test display page
├── example/            # Sample output HTML files
├── uploads/            # Temporary PDF storage (created automatically)
├── requirements.txt    # Python dependencies
└── README.md          # This file
```

## How It Works

### 1. PDF Processing
- Uses PyMuPDF (fitz) to extract text and block information from PDF files
- Preserves layout and structure information

### 2. Text Splitting
- Identifies the boundary between reading passage and questions
- Uses keywords like "below.", "Questions", "Choose the correct letter", etc.

### 3. Passage Structure
- Detects paragraph lettering (A, B, C, etc.)
- Identifies title and introductory text
- Preserves paragraph organization

### 4. Question Type Recognition
The application recognizes these question types:

**Single Choice Questions**
- Format: Numbered questions with A, B, C, D options

**Summary Completion**
- Format: Text with numbered blanks and lettered word bank
- Displays summary with dropdown selectors

**Paragraph Matching**
- Format: "Which paragraph contains..." statements
- Extracts paragraph letter options

**Yes/No/Not Given** or **True/False/Not Given**
- Format: Statements requiring Yes/No/Not Given answers
- Provides radio button options

**Fill-in-the-Blank**
- Format: Numbered blanks with context
- Provides text input fields

### 5. Display
- Responsive two-panel layout
- Passage on the left with paragraph letters
- Questions on the right with appropriate controls
- Clean, modern UI design

## Technical Details

### Dependencies
- **Flask**: Web framework for the application
- **PyMuPDF (fitz)**: PDF text extraction and processing
- **Werkzeug**: File upload handling and security

### Key Functions
- `extract_text_and_blocks()`: Extracts text and layout blocks from PDF
- `split_passage_questions()`: Separates passage from questions
- `structure_passage()`: Identifies paragraph structure and lettering
- `parse_questions()`: Recognizes and parses all question types
- `parse_single_choice()`: Parses multiple choice questions
- `parse_summary_completion()`: Parses summary completion with word banks
- `parse_paragraph_matching()`: Parses paragraph matching questions
- `parse_yes_no_not_given()`: Parses Yes/No/Not Given questions

## Development

To run in development mode with debug enabled:
```bash
python app.py
```

The application will run on `http://localhost:5000` with auto-reload enabled.

## Limitations

- PDF format must follow standard IELTS reading test layout
- Question type recognition depends on specific keywords and patterns
- Best results with well-formatted, text-based PDFs (not scanned images)

## Future Enhancements

- Answer key integration
- Timer functionality
- Score calculation
- Multi-passage support
- Support for scanned PDFs (OCR)
- Answer submission and storage
- User accounts and progress tracking

## License

This project is open source and available for educational purposes.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.
