import re
import asyncio
from typing import List
from pathlib import Path

chapter_patterns = [
        # r'No.[012345678910\d]+Volume',
        r'Chapter [012345678910\d]',
        r'No. [012345678910\d]',
        r'Chapter\s+\d+',
        r'CHAPTER\s+\d+',
        # r'Volume\d+',
        r'Chapter\d+',
        r'Chapter\d+',
]

async def split_novel_by_chapters(file_path: str) -> List[str]:
    """Divide the novel into chapters"""
    
    try:
        # Read the file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # If the file contains the chapter CHAPTER
        if _is_chapter_title(content):  # Files larger than 50KB
            chapters = await _split_large_novel(content)
        else:
            chapters = await _split_small_novel(content)
        
        # Make sure there is at least one chapter
        if not chapters:
            chapters = [content]
        
        return chapters
        
    except Exception as e:
        print(f"Failed to split chapter: {e}")
        # Return the entire document as a chapter
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return [f.read()]
        except:
            return ["Unable to read file contents"]

async def _split_large_novel(content: str) -> List[str]:
    """Dividing a large novel"""
    
    # # Try splitting by chapter title
    # chapter_patterns = [
    #    r'No.[012345678910\d]+Volume',
    #    r'Chapter [012345678910\d]',
    #    r'No. [012345678910\d]',
    #    r'Chapter\s+\d+',
    #    r'CHAPTER\s+\d+',
    #    r'Volume\d+',
    #    r'Chapter\d+',
    #    r'Chapter\d+',
    # ]
    
    chapters = []
    
    for pattern in chapter_patterns:
        matches = list(re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE))
        if len(matches) >= 2:  # At least 2 chapter markers found
            chapters = _extract_chapters_by_pattern(content, matches)
            if chapters:
                break
        if len(matches) == 1:  # At least 2 chapter markers found
            chapters = _extract_chapters_by_pattern(content, matches)
            if chapters:
                break
            
    
    # If no chapter marker is found, split by paragraph
    if not chapters:
        chapters = await _split_by_paragraphs(content)
    
    return chapters

async def _split_small_novel(content: str) -> List[str]:
    """Split short stories"""
    
    # Try simple chapter splitting
    lines = content.split('\n')
    chapters = []
    current_chapter = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check if it is a chapter title
        if _is_chapter_title(line):
            if current_chapter:
                chapters.append('\n'.join(current_chapter))
                current_chapter = []
            current_chapter.append(line)
        else:
            current_chapter.append(line)
    
    # Add the last chapter
    if current_chapter:
        chapters.append('\n'.join(current_chapter))
    
    print(chapters)
    # If there is only one chapter, split it into paragraphs
    if len(chapters) == 1:
        chapters = await _split_by_paragraphs(content)
    
    return chapters

def _extract_chapters_by_pattern(content: str, matches: List) -> List[str]:
    """Extract chapters based on matching patterns"""
    chapters = []
    
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        
        chapter_content = content[start:end].strip()
        if chapter_content:
            chapters.append(chapter_content)
    
    return chapters

async def _split_by_paragraphs(content: str) -> List[str]:
    """Split by paragraph"""
    
    paragraphs = content.split('\n\n')  # Double line breaks separate paragraphs
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    if len(paragraphs) < 3:
        # If there are too few paragraphs, split them by single line breaks
        paragraphs = content.split('\n')
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    # Combine paragraphs into chapters (every 3-5 paragraphs form a chapter)
    chapters = []
    current_chapter = []
    
    for i, paragraph in enumerate(paragraphs):
        current_chapter.append(paragraph)
        
        # Every 3-5 paragraphs are combined into a chapter
        if len(current_chapter) >= 3 and (i + 1) % 4 == 0:
            chapters.append('\n\n'.join(current_chapter))
            current_chapter = []
    
    # Add remaining paragraphs
    if current_chapter:
        chapters.append('\n\n'.join(current_chapter))
    
    return chapters

def _is_chapter_title(line: str) -> bool:
    """Determine whether it is a chapter title"""
    
    # Length check
    # if len(line) > 100:
    #     return False
    
    # Chapter Title Mode
    # patterns = [
    #     r'No.[012345678910\d]+Volume',
    #     r'Chapter [012345678910\d]',
    #     r'No. [012345678910\d]',
    #     r'Chapter\s+\d+',
    #     r'CHAPTER\s+\d+',
    #     r'Volume\d+',
    #     r'Chapter\d+',
    #     r'Chapter\d+',
    #     r'^\d+\.', # Starts with a number
    #     r'^\d+\s+', # Numbers begin with a space
    # ]
    
    for pattern in chapter_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    
    return False

def extract_author(content: str) -> str:
    """Extract author information from novel content (matches 'author:' or 'author:' format)"""
    # Match pattern: author followed by a colon (full-width/half-width), then the author's name (not a line break character)
    pattern = r'作者[:：]\s*([^\n]+)'
    match = re.search(pattern, content, re.IGNORECASE)
    return match.group(1).strip() if match else ""

def extract_book_title(text: str) -> str:
        """Extract book titles from text (supports "Book Title" and "Book Title:XXX" formats)"""
        # Then match the "Book Title:" format (e.g., "A Mortal's Journey to Immortality").
        pattern_2 = r'Title [:：]\s*([^\n]+)'  # Matches the non-newline content after "Book Title:"
        match_2 = re.search(pattern_2, text, re.IGNORECASE)
        if match_2:
            return match_2.group(1).strip()
        
         # Prioritize matching book titles in quotation marks (e.g., "A Mortal's Journey to Immortality")
        pattern_1 = r'《([^》]+)》'  # Match the content between "and"
        match_1 = re.search(pattern_1, text)
        if match_1:
            return match_1.group(1).strip()
        return ""

def main():
    """Test chapter splitting function"""
    import sys
    if len(sys.argv) < 2:
        print("Usage: python file_utils.py <novel file path>")
        return

    file_path = sys.argv[1]
    if not Path(file_path).exists():
        print(f"Error: File {file_path} does not exist")
        return

    try:
        # Read file contents for author extraction
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract author
        author = extract_author(content)
        print(f"Extracted author: {author if author else 'Author information not found'}")

        # Extract author
        book_title = extract_book_title(content)
        print(f"Extract the book title: {book_title if book_title else 'No book title information found'}")

        # Chapter Split Test
        chapters = asyncio.run(split_novel_by_chapters(file_path))
        print(f"Successfully split into {len(chapters)} chapters")
        for i, chapter in enumerate(chapters, 1):
            preview = chapter[:100].replace('\n', ' ')  # Display the first 100 characters (newlines replaced with spaces)
            print(f"Chapter {i} {len(chapter)} preview: {preview}...")
    except Exception as e:
        print(f"Test failed: {str(e)}")

if __name__ == "__main__":
    main()
