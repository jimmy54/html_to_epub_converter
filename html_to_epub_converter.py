#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML to EPUB Converter
This script converts multiple HTML files into a single EPUB ebook,
organizing chapters by date found in directory names.
"""

import os
import re
import datetime
from bs4 import BeautifulSoup
from ebooklib import epub
import logging
import shutil
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HTMLtoEPUBConverter:
    def __init__(self, source_dir, output_file="布达文萨文集.epub"):
        """Initialize the converter with source directory and output file name."""
        self.source_dir = source_dir
        self.output_file = output_file
        self.book = epub.EpubBook()
        self.chapters = []
        self.spine = ['nav']
        self.toc = []
        
        # Set book metadata
        self.book.set_identifier('id123456789')
        self.book.set_title('布达文萨文集')
        self.book.set_language('zh-CN')
        self.book.add_author('Buddhavamsa')
        
        # Create book CSS
        self.style = '''
        @namespace epub "http://www.idpf.org/2007/ops";
        body {
            font-family: "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans CN", serif;
            margin: 5%;
            text-align: justify;
        }
        h1, h2 {
            text-align: center;
            font-weight: bold;
            margin-top: 1em;
            margin-bottom: 1em;
        }
        p {
            margin: 1em 0;
            line-height: 1.5em;
        }
        .center {
            text-align: center;
        }
        .strong {
            font-weight: bold;
        }
        img {
            max-width: 100%;
            height: auto;
        }
        '''
        
        css_file = epub.EpubItem(
            uid="style_default",
            file_name="style/default.css",
            media_type="text/css",
            content=self.style
        )
        self.book.add_item(css_file)
    
    def extract_date_from_dirname(self, dirname):
        """Extract date from the directory name."""
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', dirname)
        if date_match:
            try:
                return datetime.datetime.strptime(date_match.group(1), '%Y-%m-%d')
            except ValueError:
                return datetime.datetime.strptime('2000-01-01', '%Y-%m-%d')  # Default date
        return datetime.datetime.strptime('2000-01-01', '%Y-%m-%d')  # Default date
    
    def clean_html_content(self, html_content):
        """Clean HTML content to make it suitable for EPUB."""
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Remove scripts, styles, and other unwanted elements
        for tag in soup.find_all(['script', 'style', 'meta', 'link', 'noscript', 'iframe']):
            tag.decompose()
        
        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, str) and text.strip().startswith('<!--')):
            comment.extract()
        
        # Extract the title
        title = ""
        title_tag = soup.find('h1')
        if title_tag:
            title = title_tag.text.strip()
        
        # Extract the main content
        content_div = soup.find('div', id='js_content')
        if not content_div:
            content_div = soup.find('div', class_='rich_media_content')
        
        if not content_div:
            return title, "<p>Content not found</p>"
            
        # Create a copy of the content to work with
        content_copy = BeautifulSoup(str(content_div), 'lxml')
        
        # Remove footer elements that contain author info, email, etc.
        self._remove_footer_elements(content_copy)
        
        # Process the cleaned content
        processed_content = str(content_copy.find('div'))
        
        # Preserve paragraph formatting and spacing
        processed_content = self._preserve_formatting(processed_content)
        
        # Process images - replace relative URLs with absolute ones or base64
        soup_content = BeautifulSoup(processed_content, 'lxml')
        for img in soup_content.find_all('img'):
            src = img.get('src', '')
            if src.startswith('./assets/'):
                # Keep track of image files to include them in the EPUB
                self.image_files_to_process.append(src)
                # Update the image path for EPUB
                img['src'] = os.path.basename(src)
            
            # Remove unnecessary attributes
            for attr in list(img.attrs):
                if attr != 'src' and attr != 'alt':
                    del img[attr]
        
        return title, str(soup_content)
    
    def _preserve_formatting(self, html_content):
        """Preserve paragraph formatting, spacing, and styles for better readability."""
        # Keep essential styles for paragraphs while removing clutter
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Ensure paragraphs have proper spacing
        for p in soup.find_all('p'):
            # Keep text-align styles which are important for formatting
            style = p.get('style', '')
            new_style = []
            
            # Extract and keep only essential style properties
            if 'text-align' in style:
                align_match = re.search(r'text-align:\s*([^;]+)', style)
                if align_match:
                    new_style.append(f"text-align: {align_match.group(1)}")
            
            if 'font-weight' in style and 'bold' in style:
                new_style.append("font-weight: bold")
                
            if 'text-indent' in style:
                indent_match = re.search(r'text-indent:\s*([^;]+)', style)
                if indent_match:
                    new_style.append(f"text-indent: {indent_match.group(1)}")
            
            # Set the new simplified style
            if new_style:
                p['style'] = '; '.join(new_style)
            else:
                # If no essential styles, remove the style attribute completely
                if 'style' in p.attrs:
                    del p['style']
        
        # Handle headings to ensure they stand out properly
        for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            h['style'] = "text-align: center; font-weight: bold;"
        
        # Ensure proper spacing between paragraphs
        html = str(soup)
        # Add spacing between paragraphs if needed
        html = html.replace('</p><p', '</p>\n<p')
        
        return html
    
    def _remove_footer_elements(self, content_div):
        """Remove unnecessary footer elements like author info, emails, and certain images."""
        # 1. Try to find paragraphs containing email addresses or author info
        email_patterns = [
            r'\[email[^\]]*\]', 
            r'邮箱', 
            r'@', 
            r'__cf_email__'
        ]
        
        author_patterns = [
            'Buddhavamsa', 
            '布达文萨',
            '公众号',
            '关注'
        ]
        
        # Check paragraphs from the end of content, as footers are usually at the bottom
        paragraphs = content_div.find_all('p')
        if len(paragraphs) < 3:
            return  # Too few paragraphs, likely no footer
            
        # Start from the end to check for footer elements
        footer_elements = []
        
        # Process the last 5 paragraphs (or fewer if there aren't that many)
        for i in range(min(5, len(paragraphs))):
            p = paragraphs[-(i+1)]  # Start from the last paragraph
            p_text = p.get_text().strip()
            
            # Check if this paragraph contains email or author patterns
            is_footer = False
            
            # Check for email patterns
            for pattern in email_patterns:
                if re.search(pattern, str(p)):
                    is_footer = True
                    break
                    
            # Check for author patterns if not already marked as footer
            if not is_footer:
                for pattern in author_patterns:
                    if pattern in p_text:
                        is_footer = True
                        break
            
            # Check for image-only paragraphs at the end that might be QR codes or logos
            if not is_footer and p.find('img') and len(p_text.strip()) < 3:  # Very little text + has image
                is_footer = True
                
            # Check for style attributes that indicate footer content
            if not is_footer and ('color: rgb(34, 34, 34)' in str(p) or 'Helvetica Neue' in str(p)):
                if len(p_text.strip()) < 30:  # Short text with specific styling is likely footer
                    is_footer = True
            
            if is_footer:
                footer_elements.append(p)
            else:
                # If we find a non-footer paragraph, stop checking 
                # (assuming footers are contiguous at the end)
                break
                
        # Remove identified footer elements
        for element in footer_elements:
            element.decompose()
    
    def process_directory(self):
        """Process the main directory to find all HTML files."""
        logger.info(f"Processing directory: {self.source_dir}")
        
        # Get a list of all subdirectories (article directories)
        all_dirs = []
        for item in os.listdir(self.source_dir):
            item_path = os.path.join(self.source_dir, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                # Check if index.html exists in the directory
                if os.path.exists(os.path.join(item_path, 'index.html')):
                    all_dirs.append((item, item_path))
        
        # Sort directories by date
        all_dirs.sort(key=lambda x: self.extract_date_from_dirname(x[0]))
        
        logger.info(f"Found {len(all_dirs)} article directories")
        return all_dirs
    
    def process_html_file(self, dir_info, chapter_id):
        """Process a single HTML file."""
        dir_name, dir_path = dir_info
        html_path = os.path.join(dir_path, 'index.html')
        
        if not os.path.exists(html_path):
            logger.warning(f"HTML file not found: {html_path}")
            return None
        
        logger.info(f"Processing: {html_path}")
        
        # Initialize the list to track image files for this chapter
        self.image_files_to_process = []
        
        # Read and clean the HTML content
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        title, clean_content = self.clean_html_content(html_content)
        if not title:
            title = dir_name
        
        # Create EPUB chapter
        chapter = epub.EpubHtml(
            title=title,
            file_name=f'chapter_{chapter_id}.xhtml',
            lang='zh-CN'
        )
        
        # Format the date for the chapter header
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', dir_name)
        date_str = date_match.group(1) if date_match else ""
        
        # Set chapter content with title and date
        chapter_content = f"""
        <h1>{title}</h1>
        <p class="center"><strong>{date_str}</strong></p>
        {clean_content}
        """
        chapter.content = chapter_content
        chapter.add_item(self.book.get_item_with_id('style_default'))
        
        # Process images for this chapter
        assets_dir = os.path.join(dir_path, 'assets')
        if os.path.exists(assets_dir):
            for img_path in self.image_files_to_process:
                full_img_path = os.path.join(dir_path, img_path)
                if os.path.exists(full_img_path):
                    # Determine image type
                    img_ext = os.path.splitext(full_img_path)[1].lower()
                    if img_ext == '.jpg' or img_ext == '.jpeg':
                        media_type = 'image/jpeg'
                    elif img_ext == '.png':
                        media_type = 'image/png'
                    elif img_ext == '.gif':
                        media_type = 'image/gif'
                    elif img_ext == '.svg':
                        media_type = 'image/svg+xml'
                    else:
                        media_type = 'image/jpeg'  # Default
                    
                    # Read image file
                    with open(full_img_path, 'rb') as img_file:
                        img_content = img_file.read()
                    
                    # Add image to the book
                    img_name = os.path.basename(img_path)
                    img_item = epub.EpubItem(
                        uid=f'image_{chapter_id}_{img_name}',
                        file_name=f'images/{img_name}',
                        media_type=media_type,
                        content=img_content
                    )
                    self.book.add_item(img_item)
                    
                    # Update image source in chapter content to point to the correct path
                    chapter.content = chapter.content.replace(
                        f'src="{img_name}"', 
                        f'src="images/{img_name}"'
                    )
        
        return chapter, title
    
    def create_epub(self):
        """Create the EPUB file from processed HTML files."""
        # Process all directories and create chapters
        all_dirs = self.process_directory()
        
        # Create a cover page
        cover = epub.EpubHtml(title='封面', file_name='cover.xhtml', lang='zh-CN')
        cover.content = f'''
        <html>
        <head>
            <title>布达文萨文集</title>
        </head>
        <body>
            <div style="text-align: center; padding-top: 20%;">
                <h1>布达文萨文集</h1>
                <p>共收录 {len(all_dirs)} 篇文章</p>
                <p>生成日期: {datetime.datetime.now().strftime('%Y-%m-%d')}</p>
            </div>
        </body>
        </html>
        '''
        cover.add_item(self.book.get_item_with_id('style_default'))
        self.book.add_item(cover)
        self.spine.append(cover)
        
        # Create a table of contents page
        toc_page = epub.EpubHtml(title='目录', file_name='toc.xhtml', lang='zh-CN')
        toc_content = '<h1>目录</h1><ul>'
        
        # Process each directory (article)
        for i, dir_info in enumerate(all_dirs):
            result = self.process_html_file(dir_info, i+1)
            if result:
                chapter, title = result
                self.book.add_item(chapter)
                self.chapters.append(chapter)
                self.spine.append(chapter)
                self.toc.append(epub.Link(chapter.file_name, title, f'chapter_{i+1}'))
                
                # Add entry to TOC page
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', dir_info[0])
                date_str = date_match.group(1) if date_match else ""
                toc_content += f'<li><a href="{chapter.file_name}">{date_str} - {title}</a></li>'
        
        toc_content += '</ul>'
        toc_page.content = toc_content
        toc_page.add_item(self.book.get_item_with_id('style_default'))
        self.book.add_item(toc_page)
        self.spine.insert(1, toc_page)  # Insert after cover, before chapters
        
        # Add TOC page to navigation
        self.toc.insert(0, epub.Link('toc.xhtml', '目录', 'toc'))
        
        # Set the book spine and table of contents
        self.book.spine = self.spine
        self.book.toc = self.toc
        
        # Add navigation files
        self.book.add_item(epub.EpubNcx())
        self.book.add_item(epub.EpubNav())
        
        # Write the epub file
        epub.write_epub(self.output_file, self.book, {})
        logger.info(f"EPUB created successfully: {self.output_file}")
        return self.output_file

if __name__ == "__main__":
    # Directory containing HTML files
    source_directory = os.path.abspath(os.path.dirname(__file__))
    output_file = os.path.join(source_directory, "布达文萨文集.epub")
    
    # Create converter and generate EPUB
    converter = HTMLtoEPUBConverter(source_directory, output_file)
    epub_file = converter.create_epub()
    
    print(f"EPUB book created: {epub_file}")
    print(f"Total size: {os.path.getsize(epub_file) / (1024*1024):.2f} MB")
