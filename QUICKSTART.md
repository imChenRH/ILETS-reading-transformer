# Quick Start Guide

## Setup (5 minutes)

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the application:**
   ```bash
   python app.py
   ```

3. **Open your browser:**
   - Navigate to: http://localhost:5000

## Using the Application

### Step 1: Upload PDF
- Click "Choose File" and select your IELTS reading PDF
- Click "Upload" to process the file

### Step 2: View Results
- The passage will appear on the left panel with:
  - Title
  - Introduction (if present)
  - Paragraphs labeled A, B, C, etc.

- Questions will appear on the right panel with:
  - Appropriate input controls for each question type
  - Options displayed clearly

### Supported Question Types

The application now recognizes all 10 IELTS question types:

1. **Multiple Choice Questions (MCQ)** - Radio buttons with A, B, C, D options
2. **True/False/Not Given** - Three-option radio buttons for factual statements
3. **Yes/No/Not Given** - Three-option radio buttons for opinion-based statements
4. **Matching Headings** - Dropdown menus to match roman numeral headings to paragraphs
5. **Matching Information** - Radio buttons or text input for paragraph matching
6. **Matching Features** - Radio buttons to match statements to persons/entities
7. **Matching Sentence Endings** - Dropdown menus to complete sentences
8. **Sentence Completion** - Text input fields for fill-in-the-blank questions
9. **Summary/Note/Table/Flow-Chart Completion** - Dropdown menus with word bank options
10. **Diagram Label Completion** - Text input fields to label diagrams from passage
11. **Short-Answer Questions** - Text input with word limit instructions (e.g., NO MORE THAN THREE WORDS)

## Testing the Installation

Run the test script to verify everything is working:
```bash
python test_functionality.py
```

You should see:
```
✓ All imports successful
✓ Passage extracted: ...
✓ Questions extracted: ...
✓ All core functionality tests passed!
```

## Troubleshooting

### "Module not found" error
```bash
pip install -r requirements.txt
```

### Port 5000 already in use
Edit `app.py` and change the last line to:
```python
app.run(debug=True, port=8080)
```

### PDF not processing correctly
- Ensure the PDF is text-based (not a scanned image)
- Check that the PDF follows standard IELTS format
- Verify the PDF contains clear section markers

## Example Files

Check the `example/` directory for sample output HTML files showing how processed tests look.

## Need Help?

- Check the main README.md for detailed documentation
- Open an issue on GitHub
- Review the example HTML files in the `example/` directory
