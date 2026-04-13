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

def cleanup_html(html_content):
    """Clean HTML using selectors for blogTitle and article-content-block."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. Extract Title: h1#blogTitle
        title_tag = soup.find('h1', id='blogTitle')
        article_title = title_tag.get_text(strip=True) if title_tag else "Untitled"
        
        # 2. Extract Content: div#article-content-block
        article_container = soup.find('div', id='article-content-block')
        if not article_container:
            return None, article_title
        
        # 3. Cleanup Unwanted Elements
        for tag in article_container.find_all(['img', 'script', 'style']):
            tag.decompose()
        for unwanted in article_container.find_all('div', class_='article-toc_right authArticleBox'):
            unwanted.decompose()
        
        # 4. Structure Output
        output_soup = BeautifulSoup('', 'html.parser')
        h1 = output_soup.new_tag('h1')
        h1.string = article_title
        output_soup.append(h1)
        output_soup.append(article_container)
        
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

def wrap_html_content(raw_html, title):
    """Wrap raw scraped HTML in a styled HTML boilerplate."""
    full_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 800px;
                margin: 0 auto;
                padding: 2rem;
            }}
            h1, h2, h3 {{ color: #111; line-height: 1.25; }}
            a {{ color: #0066cc; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            pre {{ background: #f4f4f4; padding: 1rem; overflow-x: auto; border-radius: 4px; }}
            blockquote {{ border-left: 4px solid #ddd; padding-left: 1rem; color: #666; font-style: italic; }}
            table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f8f8f8; }}
        </style>
    </head>
    <body>
        {raw_html}
    </body>
    </html>
    """
    return full_html

def scrape_url_lightweight(url):
    """Fetch content using HTTP GET (No browser required). Returns MD and HTML."""
    try:
        with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
            response = client.get(url)
            if response.status_code == 200:
                html_content, title = cleanup_html(response.text)
                if html_content:
                    md_content = convert_to_markdown(html_content)
                    return md_content, html_content, title
    except Exception as e:
        print(f"Error scraping {url}: {e}")
    return None, None, "Untitled"

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
                    md, raw_html, title = scrape_url_lightweight(url)
                    
                    if md and raw_html:
                        filename_base = f"poonawalla_{slugify(title)}"
                        
                        # 1. Save Markdown (For Streamlit Preview)
                        with open(OUTPUT_DIR / f"{filename_base}.md", 'w', encoding='utf-8') as f:
                            f.write(f"**Source:** {url}\n\n{md}")
                            
                        # 2. Save HTML (For exact styling & table preservation)
                        styled_html = wrap_html_content(f"<p><strong>Source:</strong> <a href='{url}'>{url}</a></p>\n{raw_html}", title)
                        with open(OUTPUT_DIR / f"{filename_base}.html", 'w', encoding='utf-8') as f:
                            f.write(styled_html)
                            
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
                        
                        # 2. Download HTML Button
                        html_path = md_path.with_suffix('.html')
                        if html_path.exists():
                            with open(html_path, "r", encoding="utf-8") as f:
                                html_data = f.read()
                                
                            col3.download_button(
                                label="Download",
                                data=html_data,
                                file_name=html_path.name,
                                mime="text/html",
                                key=f"dl_html_{md_path.name}"
                            )
                        else:
                            col3.write("HTML file missing")
                        
                        # Show the preview window when the state is True
                        if st.session_state[state_key]:
                            st.divider()
                            with open(md_path, "r", encoding="utf-8") as f:
                                st.markdown(f.read())

if __name__ == "__main__":
    main()