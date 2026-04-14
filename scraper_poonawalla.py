import streamlit as st
import httpx
import sys
import os
import re
import datetime
import html2text
from bs4 import BeautifulSoup
from pathlib import Path

# --- Configuration ---
CRAWLER_NAME = "poonawalla_fincorp"
BASE_DATA_DIR = Path("scraped_articles")
OUTPUT_DIR = BASE_DATA_DIR / CRAWLER_NAME
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ============================================================================
# UTILITIES & LOGIC
# ============================================================================

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text).strip('_')
    return text

def cleanup_html(html_content, url):
    """Clean HTML using selectors based on URL type."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. Check if it's a blog page via URL
        if '/blogs/' in url.lower():
            # --- BLOG PAGE LOGIC ---
            title_tag = soup.find('h1', id='blogTitle')
            article_title = title_tag.get_text(strip=True) if title_tag else "Untitled Blog"
            
            article_container = soup.find('div', id='article-content-block')
            if not article_container:
                return None, article_title
            
            # Cleanup Unwanted Elements
            for tag in article_container.find_all(['img', 'script', 'style']):
                tag.decompose()
            for unwanted in article_container.find_all('div', class_='article-toc_right authArticleBox'):
                unwanted.decompose()
            
            # Structure Output
            output_soup = BeautifulSoup('', 'html.parser')
            h1 = output_soup.new_tag('h1')
            h1.string = article_title
            output_soup.append(h1)
            output_soup.append(article_container)
            
            return str(output_soup), article_title
            
        else:
            # --- REGULAR WEBPAGE LOGIC ---
            # Fallback title
            page_title_tag = soup.find('title')
            article_title = page_title_tag.get_text(strip=True) if page_title_tag else "Untitled Webpage"
            
            # Grab main-content
            main_content = soup.find('div', id='main-content')
            if not main_content:
                return None, article_title
                
            # Cleanup images and footer
            for tag in main_content.find_all('img'):
                tag.decompose()
            for tag in main_content.find_all('footer'):
                tag.decompose()
            for tag in main_content.find_all('header'):
                tag.decompose()
            # Additional safety cleanup
            for tag in main_content.find_all(['script', 'style']):
                tag.decompose()
                
            # Structure Output
            output_soup = BeautifulSoup('', 'html.parser')
            h1 = output_soup.new_tag('h1')
            h1.string = article_title
            output_soup.append(h1)
            output_soup.append(main_content)
            
            return str(output_soup), article_title

    except:
        return None, "Untitled"

def convert_to_markdown(html_content):
    """Convert cleaned HTML to Markdown using html2text (for preview only)."""
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.heading_style = "ATX"
    markdown_content = h.handle(html_content)
    if markdown_content and not markdown_content.strip().startswith("#"):
        markdown_content = f"# {markdown_content.lstrip()}"
    return markdown_content

def scrape_url_lightweight(url):
    """Fetch content using HTTP GET (No browser required). Returns MD."""
    try:
        with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
            response = client.get(url)
            if response.status_code == 200:
                html_content, title = cleanup_html(response.text, url)
                if html_content:
                    md_content = convert_to_markdown(html_content)
                    return md_content, title
    except Exception as e:
        print(f"Error scraping {url}: {e}")
    return None, "Untitled"

def toggle_preview(key):
    """Callback to toggle the preview state of a specific file."""
    st.session_state[key] = not st.session_state[key]

# ============================================================================
# STREAMLIT UI
# ============================================================================

def main():
    st.set_page_config(page_title="Poonawalla Scraper", page_icon="⚡", layout="wide")
    st.title("⚡Lightning-fast Poonawalla Scraper For ContentWhale")

    tab_scrape, tab_gallery = st.tabs(["🚀 Scrape", "📚 Gallery"])

    with tab_scrape:
        url_input = st.text_area("Paste URLs (one per line):", height=150)
        if st.button("Run Scraper", type="primary"):
            urls = [u.strip() for u in url_input.split('\n') if u.strip() and "poonawallafincorp.com" in u]
            
            if not urls:
                st.warning("Please enter valid Poonawalla URLs.")
            else:
                progress = st.progress(0)
                status = st.empty()
                success_count = 0
                
                for i, url in enumerate(urls):
                    status.text(f"Scraping ({i+1}/{len(urls)}): {url}")
                    md, title = scrape_url_lightweight(url)
                    
                    if md:
                        filename_base = f"poonawalla_{slugify(title)}"
                        
                        # Save Markdown
                        with open(OUTPUT_DIR / f"{filename_base}.md", 'w', encoding='utf-8') as f:
                            f.write(f"**Source:** {url}\n\n{md}")
                            
                        success_count += 1
                    
                    progress.progress((i + 1) / len(urls))
                
                status.success(f"Processed {success_count} articles! Check the Gallery.")

    with tab_gallery:
        if OUTPUT_DIR.exists():
            # Scan for markdown files to list items in the gallery
            files = sorted(list(OUTPUT_DIR.glob("*.md")), key=os.path.getmtime, reverse=True)
            if not files:
                st.info("No files found.")
            else:
                for md_path in files:
                    with st.container(border=True):
                        col1, col2, col3 = st.columns([6, 2, 2])
                        
                        col1.markdown(f"**📄 {md_path.stem}**")
                        
                        # Manage session state for preview toggle
                        state_key = f"preview_{md_path.name}"
                        if state_key not in st.session_state:
                            st.session_state[state_key] = False
                            
                        # 1. Preview / Close Preview Button
                        btn_label = "Close Preview" if st.session_state[state_key] else "Preview"
                        col2.button(
                            btn_label, 
                            key=f"prev_btn_{md_path.name}",
                            on_click=toggle_preview,
                            args=(state_key,)
                        )
                        
                        # 2. Download Markdown Button
                        with open(md_path, "r", encoding="utf-8") as f:
                            md_data = f.read()
                            
                        col3.download_button(
                            label="Download",
                            data=md_data,
                            file_name=md_path.name,
                            mime="text/markdown",
                            key=f"dl_md_{md_path.name}"
                        )
                        
                        # Show the preview window when the state is True
                        if st.session_state[state_key]:
                            st.divider()
                            st.markdown(md_data)

if __name__ == "__main__":
    main()