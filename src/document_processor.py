#!/usr/bin/env python3

import os
import json
import PyPDF2
from loguru import logger
from typing import Optional, Dict, Any

class DocumentProcessor:
    """Class for processing and extracting text from various document formats"""
    
    def __init__(self):
        """Initialize the document processor"""
        self.supported_formats = {
            '.pdf': self._process_pdf,
            '.json': self._process_json
        }
    
    def extract_text(self, file_path: str) -> str:
        """
        Extract text from a document file
        
        Args:
            file_path: Path to the document file
            
        Returns:
            str: Extracted text content
        """
        try:
            # Get file extension
            _, ext = os.path.splitext(file_path)
            ext = ext.lower()
            
            # Check if format is supported
            if ext not in self.supported_formats:
                raise ValueError(f"Unsupported file format: {ext}")
            
            # Process the file
            return self.supported_formats[ext](file_path)
            
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {str(e)}")
            raise
    
    def _process_pdf(self, file_path: str) -> str:
        """
        Process a PDF file and extract text
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            str: Extracted text content
        """
        try:
            text_content = []
            
            with open(file_path, 'rb') as file:
                # Create PDF reader object
                pdf_reader = PyPDF2.PdfReader(file)
                
                # Get number of pages
                num_pages = len(pdf_reader.pages)
                logger.info(f"Processing PDF with {num_pages} pages")
                
                # Extract text from each page
                for page_num in range(num_pages):
                    page = pdf_reader.pages[page_num]
                    text_content.append(page.extract_text())
                    logger.debug(f"Processed page {page_num + 1}/{num_pages}")
            
            # Join all text content
            return '\n'.join(text_content)
            
        except Exception as e:
            logger.error(f"Error processing PDF {file_path}: {str(e)}")
            raise
    
    def _process_json(self, file_path: str) -> str:
        """
        Process a JSON file and extract text content
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            str: Extracted text content
        """
        try:
            with open(file_path, 'r') as file:
                data = json.load(file)
                
                # Handle different JSON structures
                if isinstance(data, dict):
                    # If it's a dictionary, try to find text content
                    text_content = self._extract_text_from_dict(data)
                elif isinstance(data, list):
                    # If it's a list, process each item
                    text_content = []
                    for item in data:
                        if isinstance(item, dict):
                            text_content.append(self._extract_text_from_dict(item))
                        elif isinstance(item, str):
                            text_content.append(item)
                elif isinstance(data, str):
                    # If it's a string, use it directly
                    text_content = data
                else:
                    raise ValueError(f"Unsupported JSON data type: {type(data)}")
                
                # Convert to string if it's a list
                if isinstance(text_content, list):
                    return '\n'.join(text_content)
                return str(text_content)
                
        except Exception as e:
            logger.error(f"Error processing JSON {file_path}: {str(e)}")
            raise
    
    def _extract_text_from_dict(self, data: Dict[str, Any]) -> str:
        """
        Extract text content from a dictionary
        
        Args:
            data: Dictionary containing text content
            
        Returns:
            str: Extracted text content
        """
        # Common keys that might contain text content
        text_keys = ['text', 'content', 'body', 'description', 'message']
        
        # First try to find direct text content
        for key in text_keys:
            if key in data and isinstance(data[key], str):
                return data[key]
        
        # If no direct text content found, try to find nested content
        for value in data.values():
            if isinstance(value, dict):
                return self._extract_text_from_dict(value)
            elif isinstance(value, list):
                text_parts = []
                for item in value:
                    if isinstance(item, dict):
                        text_parts.append(self._extract_text_from_dict(item))
                    elif isinstance(item, str):
                        text_parts.append(item)
                return '\n'.join(text_parts)
        
        # If no text content found, convert the entire dictionary to string
        return str(data)

# Example usage
if __name__ == "__main__":
    processor = DocumentProcessor()
    print(processor.extract_text("example.pdf"))