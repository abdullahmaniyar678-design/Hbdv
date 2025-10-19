"""
MCQ Extractor Module
Handles PDF parsing and MCQ extraction logic
"""

import re
import os
import fitz  # PyMuPDF
from PIL import Image
import logging

logger = logging.getLogger(__name__)


def extract_mcqs_from_pdf(pdf_path: str, temp_dir: str) -> list:
    """
    Extract MCQs, topics, images, and links from a PDF file
    
    Args:
        pdf_path: Path to the PDF file
        temp_dir: Temporary directory for storing images
        
    Returns:
        List of dictionaries containing topics and questions
    """
    try:
        doc = fitz.open(pdf_path)
        logger.info(f"Opened PDF with {len(doc)} pages")
        
        # Extract all text and metadata
        full_text = ""
        images = []
        links = []
        
        for page_num, page in enumerate(doc):
            # Extract text
            full_text += page.get_text()
            
            # Extract images
            page_images = extract_images_from_page(page, page_num, temp_dir)
            images.extend(page_images)
            
            # Extract links
            page_links = extract_links_from_page(page)
            links.extend(page_links)
        
        doc.close()
        
        # Parse the text to extract structured MCQ data
        structured_data = parse_mcqs(full_text, images, links)
        
        logger.info(f"Extracted {len(structured_data)} topics with questions")
        return structured_data
        
    except Exception as e:
        logger.error(f"Error extracting MCQs from PDF: {str(e)}")
        return []


def extract_images_from_page(page, page_num: int, temp_dir: str) -> list:
    """Extract images from a PDF page and save them"""
    images = []
    
    try:
        image_list = page.get_images(full=True)
        
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = page.parent.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            # Save image to temp directory
            image_filename = f"page{page_num}_img{img_index}.{image_ext}"
            image_path = os.path.join(temp_dir, image_filename)
            
            with open(image_path, "wb") as img_file:
                img_file.write(image_bytes)
            
            images.append({
                'page': page_num,
                'index': img_index,
                'path': image_path
            })
            
    except Exception as e:
        logger.error(f"Error extracting images from page {page_num}: {str(e)}")
    
    return images


def extract_links_from_page(page) -> list:
    """Extract hyperlinks from a PDF page"""
    links = []
    
    try:
        link_list = page.get_links()
        
        for link in link_list:
            if 'uri' in link:
                uri = link['uri']
                # Check if it's a video or explanation link
                if any(keyword in uri.lower() for keyword in ['youtube', 'video', 'watch', 'explanation']):
                    links.append(uri)
                    
    except Exception as e:
        logger.error(f"Error extracting links: {str(e)}")
    
    return links


def parse_mcqs(text: str, images: list, links: list) -> list:
    """
    Parse extracted text to identify topics, questions, options, and answers
    
    Args:
        text: Full text from PDF
        images: List of extracted image paths
        links: List of extracted hyperlinks
        
    Returns:
        Structured list of topics and questions
    """
    lines = text.split('\n')
    structured_data = []
    current_topic = None
    current_question = None
    current_options = []
    question_counter = 0
    image_counter = 0
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        if not line:
            continue
        
        # Detect topic/heading (all caps or bold-like patterns)
        if is_topic(line):
            # Save previous question if exists
            if current_question:
                save_question(structured_data, current_topic, current_question, 
                            current_options, images, links, image_counter)
                current_question = None
                current_options = []
            
            # Create new topic
            current_topic = clean_topic(line)
            structured_data.append({
                'topic': current_topic,
                'questions': []
            })
            continue
        
        # Detect question
        if is_question(line):
            # Save previous question if exists
            if current_question:
                save_question(structured_data, current_topic, current_question, 
                            current_options, images, links, image_counter)
                image_counter += 1
            
            # Start new question
            current_question = {
                'question': clean_question(line),
                'options': [],
                'answer': None,
                'image': None,
                'video_link': None
            }
            current_options = []
            question_counter += 1
            continue
        
        # Detect options
        if current_question and is_option(line):
            option_text = clean_option(line)
            current_options.append(option_text)
            continue
        
        # Detect answer
        if current_question and is_answer(line):
            answer_text = clean_answer(line)
            current_question['answer'] = answer_text
            continue
        
        # If it's a continuation of question or option, append it
        if current_question and not is_option(line) and not is_answer(line):
            if current_options:
                # Append to last option
                current_options[-1] += " " + line
            elif current_question['question']:
                # Append to question
                current_question['question'] += " " + line
    
    # Save last question
    if current_question:
        save_question(structured_data, current_topic, current_question, 
                    current_options, images, links, image_counter)
    
    # Remove topics with no questions
    structured_data = [topic for topic in structured_data if topic['questions']]
    
    # If no topics were found, create a default one
    if not structured_data:
        return []
    
    return structured_data


def is_topic(line: str) -> bool:
    """Check if a line is a topic/heading"""
    # All caps (at least 3 words)
    if line.isupper() and len(line.split()) >= 2:
        return True
    
    # Contains topic indicators
    topic_indicators = ['chapter', 'unit', 'section', 'topic', 'part']
    if any(indicator in line.lower() for indicator in topic_indicators):
        return True
    
    # Short bold-like text (heuristic: short lines that aren't questions)
    if len(line) < 50 and not any(char in line for char in ['?', '(', ')']):
        if not line[0].isdigit() and ':' not in line:
            return True
    
    return False


def is_question(line: str) -> bool:
    """Check if a line is a question"""
    # Starts with Q, Q., Question, or a number followed by dot/parenthesis
    question_patterns = [
        r'^Q\d+[\.\:)]',  # Q1. or Q1: or Q1)
        r'^Q[\.\:)]',     # Q. or Q:
        r'^\d+[\.\:)]',   # 1. or 1: or 1)
        r'^Question\s*\d*[\.\:]',  # Question or Question 1.
    ]
    
    for pattern in question_patterns:
        if re.match(pattern, line, re.IGNORECASE):
            return True
    
    # Contains question mark
    if '?' in line:
        return True
    
    return False


def is_option(line: str) -> bool:
    """Check if a line is an option"""
    # Patterns like (a), A., 1), [A], etc.
    option_patterns = [
        r'^[\(]?[A-Fa-f][\)\.]',  # (a) or A. or a)
        r'^[\(]?\d+[\)\.]',        # (1) or 1. or 1)
        r'^\[[A-Fa-f]\]',         # [A]
    ]
    
    for pattern in option_patterns:
        if re.match(pattern, line):
            return True
    
    return False


def is_answer(line: str) -> bool:
    """Check if a line contains the answer"""
    answer_indicators = [
        'answer', 'correct answer', 'correct option', 
        'ans:', 'ans.', 'solution', 'correct:'
    ]
    
    line_lower = line.lower()
    return any(indicator in line_lower for indicator in answer_indicators)


def clean_topic(line: str) -> str:
    """Clean and format topic text"""
    # Remove common prefixes
    line = re.sub(r'^(chapter|unit|section|topic|part)\s*\d*[\:\.]?\s*', '', line, flags=re.IGNORECASE)
    return line.strip()


def clean_question(line: str) -> str:
    """Clean and format question text"""
    # Remove question numbering
    line = re.sub(r'^(Q|Question)\s*\d*[\.\:\)]\s*', '', line, flags=re.IGNORECASE)
    line = re.sub(r'^\d+[\.\:\)]\s*', '', line)
    return line.strip()


def clean_option(line: str) -> str:
    """Clean and format option text"""
    # Remove option markers
    line = re.sub(r'^[\(\[]?[A-Fa-f\d][\)\.\]]\s*', '', line)
    return line.strip()


def clean_answer(line: str) -> str:
    """Clean and format answer text"""
    # Remove answer indicators
    line = re.sub(r'^(answer|correct answer|correct option|ans|solution|correct)[\:\.]?\s*', '', line, flags=re.IGNORECASE)
    return line.strip()


def save_question(structured_data: list, topic: str, question: dict, 
                 options: list, images: list, links: list, image_index: int):
    """Save a completed question to the structured data"""
    # Add options to question
    question['options'] = options
    
    # Assign image if available
    if image_index < len(images):
        question['image'] = images[image_index]['path']
    
    # Assign video link if available
    if image_index < len(links):
        question['video_link'] = links[image_index]
    
    # Find or create topic in structured data
    if not structured_data:
        structured_data.append({
            'topic': topic or 'General Questions',
            'questions': []
        })
    
    # Add question to the last topic
    structured_data[-1]['questions'].append(question)
