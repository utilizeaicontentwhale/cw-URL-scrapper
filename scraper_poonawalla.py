import os
# Required for Streamlit Cloud deployment to ensure browser binaries are present
os.system("playwright install chromium")

import streamlit as st
import asyncio
import sys
import re
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.utils import CustomHTML2Text
from pathlib import Path

# --- CROSS-PLATFORM ASYNCIO FIX ---
# Proactor is required for Playwright on Windows, but doesn't exist on Linux.
IS_WINDOWS = sys.platform == 'win32'

if IS_WINDOWS:
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except AttributeError:
        pass

# --- Configuration ---
CRAWLER_NAME = "poonawalla_fincorp"
BASE_DATA_DIR = Path("scraped_articles")
OUTPUT_DIR = BASE_DATA_DIR / CRAWLER_NAME
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_RETRIES = 3

crawler_config_scraping = CrawlerRunConfig(
    scan_full_page=True,
    wait_until="networkidle",
    page_timeout=60000,
    delay_before_return_html=1.0
)

# ============================================================================
# UTILITIES
# ============================================================================

def slugify(text):
    """Simple slugify to create safe filenames."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text).strip('_')
    return text

# ============================================================================
# SCRAPING & CLEANUP LOGIC
# ============================================================================

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
        for img in article_container.find_all('img'):
            img.decompose()
        # Remove TOC and Author Box
        for unwanted in article_container.find_all('div', class_='article-toc_right authArticleBox'):
            unwanted.decompose()
        for tag in article_container.find_all(['script', 'style']):
            tag.decompose()
        
        # 4. Structure Output
        output_soup = BeautifulSoup('', 'html.parser')
        title_h1 = output_soup.new_tag('h1')
        title_h1.string = article_title
        output_soup.append(title_h1)
        output_soup.append(article_container)
        
        return str(output_soup), article_title
    except Exception:
        return None, "Untitled"

def convert_to_markdown(html_content):
    """Convert cleaned HTML to Markdown."""
    h = CustomHTML2Text()
    h.ignore_links = False
    h.heading_style = "ATX"
    h.topheadinglevel = 1
    markdown_content = h.handle(html_content)
    
    lines = markdown_content.splitlines()
    if lines and not lines[0].strip().startswith("#"):
        lines[0] = f"# {lines[0].strip()}"
    return "\n".join(lines)

async def scrape_url(url, crawler):
    """Fetch and process a single URL."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await crawler.arun(url, config=crawler_config_scraping)
            if not result.success:
                continue
            
            cleaned_html, title = cleanup_html(result.html)
            if not cleaned_html:
                return None, title
            
            md = convert_to_markdown(cleaned_html)
            return md, title
        except Exception:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1)
    return None, "Untitled"

# ============================================================================
# STREAMLIT UI
# ============================================================================

def main():
    st.set_page_config(page_title="Poonawalla Scraper", page_icon="📝", layout="wide")
    
    # Ensure local directory exists immediately on start
    if not BASE_DATA_DIR.exists():
        BASE_DATA_DIR.mkdir(parents=True)
        st.info(f"Created data directory: `{BASE_DATA_DIR}`")

    st.title("📝 Poonawalla Fincorp Scraper Tool")

    # Sidebar Info
    with st.sidebar:
        st.header("Storage Info")
        st.write(f"📁 **Root Folder:** `{BASE_DATA_DIR.absolute()}`")
        st.write(f"📄 **Articles Subfolder:** `{CRAWLER_NAME}`")
        if st.button("Clear Cache/Refresh"):
            st.rerun()

    # Tab Setup
    tab_scrape, tab_gallery = st.tabs(["🚀 Scrape Articles", "📚 Scraped Files Gallery"])

    # --- TAB 1: SCRAPING LOGIC ---
    with tab_scrape:
        st.markdown("### Start a New Scraping Job")
        url_input = st.text_area(
            "Paste URLs from `poonawallafincorp.com` here (one per line):", 
            height=200, 
            placeholder="https://poonawallafincorp.com/blogs/..."
        )

        if st.button("Run Scraper", type="primary"):
            urls = [u.strip() for u in url_input.split('\n') if u.strip()]
            valid_urls = [u for u in urls if "poonawallafincorp.com" in u]
            
            if not valid_urls:
                st.warning("Please enter at least one valid URL.")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                results_list = []

                async def run_scraping():
                    async with AsyncWebCrawler() as crawler:
                        for i, url in enumerate(valid_urls):
                            status_text.text(f"Processing ({i+1}/{len(valid_urls)}): {url}")
                            md_content, title = await scrape_url(url, crawler)
                            
                            if md_content:
                                safe_title = slugify(title)
                                filename = f"poonawalla_{safe_title}.md"
                                md_filepath = OUTPUT_DIR / filename
                                full_md_content = f"**Source:** {url}\n\n{md_content}"
                                
                                # Save locally (persistent)
                                with open(md_filepath, 'w', encoding='utf-8') as f:
                                    f.write(full_md_content)
                                
                                results_list.append({"title": title, "url": url})
                            
                            progress_bar.progress((i + 1) / len(valid_urls))
                        return results_list

                # Initialize loop as None to prevent UnboundLocalError
                loop = None
                try:
                    if IS_WINDOWS:
                        # Windows requires Proactor loop for Playwright
                        loop = asyncio.ProactorEventLoop()
                        asyncio.set_event_loop(loop)
                        scraped_data = loop.run_until_complete(run_scraping())
                    else:
                        # Linux (Streamlit Cloud) works with standard run() or default loop
                        try:
                            # Try running with the current loop if it exists
                            scraped_data = asyncio.run(run_scraping())
                        except RuntimeError:
                            # Fallback if a loop is already running in the background
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            scraped_data = loop.run_until_complete(run_scraping())
                    
                    status_text.success(f"Successfully processed {len(scraped_data)} articles! Go to the 'Gallery' tab to download them.")
                except Exception as e:
                    st.error(f"Scraping error: {e}")
                finally:
                    # Only close if we manually created/assigned a loop
                    if loop and not loop.is_closed():
                        loop.close()

    # --- TAB 2: GALLERY / FILE EXPLORER ---
    with tab_gallery:
        st.markdown("### Persistent Scraped Data")
        st.markdown("Files listed here are stored in your local folder and remain accessible across refreshes.")
        
        # Get list of .md files in the specific output directory
        if OUTPUT_DIR.exists():
            files = sorted([f for f in OUTPUT_DIR.iterdir() if f.suffix == '.md'], key=os.path.getmtime, reverse=True)
            
            if not files:
                st.info("No files found yet. Run a scraping job to populate this gallery.")
            else:
                st.write(f"Found {len(files)} markdown files.")
                
                # Create a simple table header
                cols = st.columns([4, 2, 2])
                cols[0].write("**File Name**")
                cols[1].write("**Created At**")
                cols[2].write("**Action**")
                st.divider()

                for f_path in files:
                    row_cols = st.columns([4, 2, 2])
                    
                    # Display filename
                    row_cols[0].text(f_path.name)
                    
                    # Display timestamp
                    mtime = os.path.getmtime(f_path)
                    import datetime
                    dt = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                    row_cols[1].text(dt)
                    
                    # Read content for the download button
                    with open(f_path, "r", encoding="utf-8") as f_obj:
                        file_data = f_obj.read()
                    
                    # Download button
                    row_cols[2].download_button(
                        label="Download",
                        data=file_data,
                        file_name=f_path.name,
                        mime="text/markdown",
                        key=f"dl_{f_path.stem}"
                    )
        else:
            st.warning("Output directory does not exist.")

if __name__ == "__main__":
    main()