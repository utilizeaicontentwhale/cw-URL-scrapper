import streamlit as st
import httpx
import sys
import os
import re
import datetime
from bs4 import BeautifulSoup
from pathlib import Path

# --- Configuration ---
CRAWLER_NAME = "poonawalla_fincorp"
BASE_DATA_DIR = Path("scraped_articles")
OUTPUT_DIR = BASE_DATA_DIR / CRAWLER_NAME
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Standard User-Agent to avoid being blocked by basic firewalls
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ============================================================================
# UTILITIES & LOGIC
# ============================================================================

def slugify(text):
    """Create a URL-safe and filename-safe version of the title."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text).strip('_')
    return text

def cleanup_html(html_content):
    """Extract content using specific selectors for Poonawalla Fincorp."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. Extract Title: h1#blogTitle
        title_tag = soup.find('h1', id='blogTitle')
        article_title = title_tag.get_text(strip=True) if title_tag else "Untitled"
        
        # 2. Extract Content: div#article-content-block
        article_container = soup.find('div', id='article-content-block')
        if not article_container:
            return None, article_title
        
        # 3. Cleanup: Remove unwanted tags
        for tag in article_container.find_all(['img', 'script', 'style', 'iframe']):
            tag.decompose()
            
        # Remove Table of Contents / Author Box
        for unwanted in article_container.find_all('div', class_='article-toc_right authArticleBox'):
            unwanted.decompose()
        
        # 4. Reconstruct clean HTML for conversion
        output_soup = BeautifulSoup('', 'html.parser')
        h1 = output_soup.new_tag('h1')
        h1.string = article_title
        output_soup.append(h1)
        output_soup.append(article_container)
        
        return str(output_soup), article_title
    except Exception as e:
        return None, f"Error: {str(e)}"

def simple_html_to_md(html_content):
    """
    A lightweight HTML to Markdown converter.
    Since we removed crawl4ai, we use a simple regex/BS4 approach 
    to maintain a zero-dependency footprint.
    """
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Process basic tags
    for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        level = int(h.name[1])
        h.replace_with(f"\n\n{'#' * level} {h.get_text().strip()}\n\n")
        
    for p in soup.find_all('p'):
        p.replace_with(f"\n{p.get_text().strip()}\n")
        
    for li in soup.find_all('li'):
        li.replace_with(f"\n* {li.get_text().strip()}")
        
    for b in soup.find_all(['b', 'strong']):
        b.replace_with(f"**{b.get_text().strip()}**")
        
    for i in soup.find_all(['i', 'em']):
        i.replace_with(f"_{i.get_text().strip()}_")

    text = soup.get_text()
    # Clean up multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def scrape_url_lightweight(url):
    """Fetch content using HTTP GET (No browser required)."""
    try:
        with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
            response = client.get(url)
            if response.status_code == 200:
                html, title = cleanup_html(response.text)
                if html:
                    md = simple_html_to_md(html)
                    return md, title
                else:
                    return None, "Content Block Not Found"
            else:
                return None, f"HTTP Error {response.status_code}"
    except Exception as e:
        return None, str(e)

# ============================================================================
# STREAMLIT UI
# ============================================================================

def main():
    st.set_page_config(page_title="Poonawalla Scraper", page_icon="⚡", layout="wide")
    
    # Ensure data directory exists
    if not BASE_DATA_DIR.exists():
        BASE_DATA_DIR.mkdir(parents=True)

    st.title("⚡ Lightning-fast Poonawalla Scraper")
    st.caption("ContentWhale Internal Tool - Zero Browser Dependencies")

    tab_scrape, tab_gallery = st.tabs(["🚀 Scrape", "📚 Gallery"])

    with tab_scrape:
        st.markdown("### 1. Input URLs")
        url_input = st.text_area("Enter Poonawalla Fincorp Blog URLs (one per line):", height=200)
        
        if st.button("Start Scraping", type="primary"):
            urls = [u.strip() for u in url_input.split('\n') if u.strip() and "poonawallafincorp.com" in u]
            
            if not urls:
                st.error("Please enter valid Poonawalla Fincorp URLs.")
            else:
                progress = st.progress(0)
                status = st.empty()
                success_count = 0
                
                for i, url in enumerate(urls):
                    status.text(f"Processing ({i+1}/{len(urls)}): {url}")
                    md, title = scrape_url_lightweight(url)
                    
                    if md:
                        safe_title = slugify(title)
                        filename = f"poonawalla_{safe_title}.md"
                        with open(OUTPUT_DIR / filename, 'w', encoding='utf-8') as f:
                            f.write(f"**Source:** {url}\n\n{md}")
                        success_count += 1
                    else:
                        st.warning(f"Failed to scrape: {url} (Reason: {title})")
                    
                    progress.progress((i + 1) / len(urls))
                
                status.success(f"Finished! Processed {success_count} articles. Check the Gallery tab.")

    with tab_gallery:
        st.markdown("### 2. View & Download Scraped Files")
        if OUTPUT_DIR.exists():
            files = sorted(list(OUTPUT_DIR.glob("*.md")), key=os.path.getmtime, reverse=True)
            if not files:
                st.info("No files found in the database.")
            else:
                st.write(f"Showing {len(files)} files found on server:")
                st.divider()
                for f_path in files:
                    c1, c2, c3 = st.columns([4, 2, 1])
                    c1.text(f"📄 {f_path.name}")
                    
                    mtime = os.path.getmtime(f_path)
                    dt = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                    c2.text(dt)
                    
                    with open(f_path, "r", encoding="utf-8") as f:
                        data = f.read()
                    
                    c3.download_button(
                        label="Download", 
                        data=data, 
                        file_name=f_path.name, 
                        mime="text/markdown", 
                        key=f"dl_{f_path.name}"
                    )
        else:
            st.error("Data directory missing.")

if __name__ == "__main__":
    main()