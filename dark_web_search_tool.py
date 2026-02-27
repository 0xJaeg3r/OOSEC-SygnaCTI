import asyncio
from typing import Dict, List, Tuple
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs

from playwright.async_api import async_playwright, Page, Browser

# Dark web search engines to query (.onion addresses)
SEARCH_URLS = {
    "ahmia": "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion",
    "abiko": "http://abikoifawyrftqivkhfxiwdjcdzybumpqrbowtudtwhrhpnykfonyzid.onion/",
    "amnesia": "http://amnesia7u5odx5xbwtpnqk3edybgud5bmiagu75bnqx2crntw5kry7ad.onion/",
}

# Search URL patterns per engine. {q} is replaced with the URL-encoded query.
# Only add patterns here that you've verified manually. Unknown engines
# fall back to /search/?q= in _build_search_url().
SEARCH_PATTERNS = {
    "ahmia": "/search/?q={q}",
}

MAX_RETRIES = 2
RETRY_DELAY = 5
DEFAULT_TIMEOUT = 90_000  # milliseconds for Playwright
MAX_CONCURRENT = 6  # max parallel pages


# ---- Browser management ----

async def _launch_tor_browser(playwright) -> Browser:
    """Launch a Chromium browser routed through Tor's SOCKS5 proxy."""
    return await playwright.chromium.launch(
        headless=True,
        proxy={"server": "socks5://127.0.0.1:9050"},
        args=[
            # Prevent DNS leaks — force all DNS through the SOCKS proxy
            "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1",
        ],
    )


async def _navigate_with_retry(page: Page, url: str) -> bool:
    """Navigate to a URL with retries. Uses two-phase wait to catch JS-rendered content."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            # Phase 1: fast initial load
            await page.goto(url, timeout=DEFAULT_TIMEOUT, wait_until="domcontentloaded")

            # Phase 2: wait for JS-rendered content (network goes quiet or
            # result elements appear). Short timeout — don't block forever
            # on sites that keep polling.
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                # networkidle timed out — page may keep streaming.
                # Fall back to waiting for common result selectors.
                result_selectors = [
                    ".result", ".search-result", "#results", ".results",
                    "[class*='result']", "li.result",
                ]
                for sel in result_selectors:
                    try:
                        await page.wait_for_selector(sel, timeout=3_000)
                        break
                    except Exception:
                        continue

            return True
        except Exception:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
                continue
            return False


# ---- Page classification ----

async def _detect_page_type(page: Page) -> str:
    """Classify what kind of page we landed on.

    Returns one of: 'search_results', 'login', 'captcha', 'error', 'directory', 'content'
    """
    content = (await page.content()).lower()

    # Check for login/registration pages
    login_indicators = [
        "login", "log in", "sign in", "signin", "username", "password",
        "register", "sign up", "signup", "authentication", "credentials",
    ]
    login_fields = await page.query_selector_all("input[type='password']")
    login_forms = await page.query_selector_all(
        "form[action*='login'], form[action*='auth'], form[action*='signin']")
    login_text_matches = sum(1 for ind in login_indicators if ind in content)

    if login_fields and login_text_matches >= 2:
        return "login"
    if login_forms:
        return "login"

    # Check for captcha
    captcha_indicators = [
        "captcha", "recaptcha", "hcaptcha", "verify you are human",
        "prove you are not a robot", "security check", "challenge",
    ]
    if any(ind in content for ind in captcha_indicators):
        captcha_elements = await page.query_selector_all(
            "img[src*='captcha'], .captcha, #captcha, .g-recaptcha, .h-captcha")
        if captcha_elements or sum(1 for c in captcha_indicators if c in content) >= 2:
            return "captcha"

    # Check for error pages
    error_indicators = [
        "404 not found", "page not found", "502 bad gateway", "503 service",
        "connection refused", "onion site not found", "unable to connect",
        "the site is down", "server error", "access denied", "403 forbidden",
    ]
    if any(ind in content for ind in error_indicators):
        return "error"

    # Check for search results
    result_selectors = [
        "li.result", ".result", ".search-result", ".search_result",
        "#results", ".results", "[class*='result']", "[id*='result']",
    ]
    for selector in result_selectors:
        if await page.query_selector(selector):
            return "search_results"

    # Check for directory/link list pages
    onion_link_count = await page.evaluate("""
        () => document.querySelectorAll('a[href*=".onion"]').length
    """)
    if onion_link_count > 5:
        return "directory"

    return "content"


# ---- Page info extractors ----

async def _extract_login_page_info(page: Page) -> Dict:
    """Extract useful metadata from a login page."""
    title = await page.title() or "No title"

    fields = await page.evaluate("""
        () => Array.from(document.querySelectorAll("input:not([type='hidden'])")).map(el => ({
            type: el.type || 'text',
            name: el.name || '',
            placeholder: el.placeholder || ''
        }))
    """)

    content = (await page.content()).lower()
    has_registration = any(w in content for w in ["register", "sign up", "create account", "new user"])

    return {
        "title": title,
        "url": page.url,
        "fields": fields,
        "notes": "Registration appears available" if has_registration else "Login only — no visible registration",
    }


async def _extract_error_info(page: Page) -> Dict:
    """Extract info from an error page."""
    title = await page.title() or "No title"
    text = await page.evaluate("() => document.body?.innerText?.substring(0, 300) || ''")
    return {
        "title": title,
        "url": page.url,
        "error_text": text.strip(),
    }


async def _extract_directory_links(page: Page, max_links: int = 20) -> List[Dict[str, str]]:
    """Extract .onion links from a directory page."""
    return await page.evaluate("""
        (maxLinks) => {
            const results = [];
            const links = document.querySelectorAll('a[href*=".onion"]');
            for (const link of links) {
                if (results.length >= maxLinks) break;
                const text = link.innerText?.trim();
                if (!text) continue;
                const href = link.href || '';
                let description = '';
                const parent = link.parentElement;
                if (parent) {
                    const parentText = parent.innerText?.trim() || '';
                    if (parentText !== text) description = parentText.substring(0, 300);
                }
                results.push({ title: text.substring(0, 200), url: href, description });
            }
            return results;
        }
    """, max_links)


# ---- Search result parsing (multi-strategy) ----

async def _parse_search_results(page: Page, max_results: int) -> List[Dict[str, str]]:
    """Try multiple parsing strategies to extract search results."""

    # Strategy 1: Structured result containers
    container_selectors = [
        "li.result", ".result", ".search-result", ".search_result",
        "[class*='result-item']", "[class*='searchresult']",
    ]
    for selector in container_selectors:
        elements = await page.query_selector_all(selector)
        if elements:
            return await _parse_result_containers(page, selector, max_results)

    # Strategy 2: Results inside a known wrapper
    wrapper_selectors = [
        "#results", ".results", "#search-results", ".search-results",
        "main", "#content", ".content",
    ]
    for wrapper_sel in wrapper_selectors:
        has_onion_links = await page.evaluate("""
            (sel) => {
                const wrapper = document.querySelector(sel);
                if (!wrapper) return false;
                return wrapper.querySelectorAll('a[href*=".onion"]').length > 0;
            }
        """, wrapper_sel)
        if has_onion_links:
            return await _parse_wrapper_links(page, wrapper_sel, max_results)

    # Strategy 3: Any .onion links on the page
    onion_count = await page.evaluate(
        "() => document.querySelectorAll('a[href*=\".onion\"]').length")
    if onion_count > 0:
        return await _parse_all_onion_links(page, max_results)

    # Strategy 4: Fallback — all links with visible text
    return await _parse_fallback(page, max_results)


async def _parse_result_containers(page: Page, selector: str,
                                    max_results: int) -> List[Dict[str, str]]:
    """Parse structured result container elements via JS for speed."""
    return await page.evaluate("""
        (args) => {
            const [selector, maxResults] = args;
            const titleSels = ['h4', 'h3', 'h2', '.title', 'a'];
            const descSels = ['p', '.description', '.snippet', '.summary', 'span', '.text', 'cite'];
            const results = [];

            for (const el of document.querySelectorAll(selector)) {
                if (results.length >= maxResults) break;

                let title = '';
                for (const ts of titleSels) {
                    const te = el.querySelector(ts);
                    if (te && te.innerText?.trim()) { title = te.innerText.trim(); break; }
                }

                let url = '';
                const linkEl = el.querySelector('a');
                if (linkEl) url = linkEl.href || '';

                let description = '';
                for (const ds of descSels) {
                    const de = el.querySelector(ds);
                    if (de) {
                        const dt = de.innerText?.trim();
                        if (dt && dt !== title) { description = dt; break; }
                    }
                }

                if (title || url) {
                    results.push({
                        title: title.substring(0, 200) || 'No title',
                        url,
                        description: description.substring(0, 500)
                    });
                }
            }
            return results;
        }
    """, [selector, max_results])


async def _parse_wrapper_links(page: Page, wrapper_sel: str,
                                max_results: int) -> List[Dict[str, str]]:
    """Parse .onion links inside a wrapper element."""
    return await page.evaluate("""
        (args) => {
            const [wrapperSel, maxResults] = args;
            const wrapper = document.querySelector(wrapperSel);
            if (!wrapper) return [];
            const results = [];
            const seen = new Set();

            for (const link of wrapper.querySelectorAll('a[href*=".onion"]')) {
                if (results.length >= maxResults) break;
                const href = link.href || '';
                if (!href || seen.has(href)) continue;
                seen.add(href);
                const text = link.innerText?.trim();
                if (!text) continue;
                let description = '';
                const parent = link.parentElement;
                if (parent) {
                    const pt = parent.innerText?.trim() || '';
                    if (pt !== text) description = pt.substring(0, 500);
                }
                results.push({ title: text.substring(0, 200), url: href, description });
            }
            return results;
        }
    """, [wrapper_sel, max_results])


async def _parse_all_onion_links(page: Page, max_results: int) -> List[Dict[str, str]]:
    """Parse all .onion links on the page."""
    return await page.evaluate("""
        (maxResults) => {
            const results = [];
            const seen = new Set();
            for (const link of document.querySelectorAll('a[href*=".onion"]')) {
                if (results.length >= maxResults) break;
                const href = link.href || '';
                if (!href || seen.has(href)) continue;
                seen.add(href);
                const text = link.innerText?.trim();
                if (!text) continue;
                let description = '';
                const parent = link.parentElement;
                if (parent) {
                    const pt = parent.innerText?.trim() || '';
                    if (pt !== text) description = pt.substring(0, 500);
                }
                results.push({ title: text.substring(0, 200), url: href, description });
            }
            return results;
        }
    """, max_results)


async def _parse_fallback(page: Page, max_results: int) -> List[Dict[str, str]]:
    """Last-resort parser: grab all links with visible text."""
    return await page.evaluate("""
        (maxResults) => {
            const results = [];
            const seen = new Set();
            for (const link of document.querySelectorAll('a')) {
                if (results.length >= maxResults) break;
                const href = link.href || '';
                if (!href || href === '#' || seen.has(href)) continue;
                const text = link.innerText?.trim();
                if (!text || text.length < 3) continue;
                seen.add(href);
                results.push({ title: text.substring(0, 200), url: href, description: '' });
            }
            return results;
        }
    """, max_results)


# ---- Build search URL ----

def _build_search_url(engine_name: str, base_url: str, query: str) -> str:
    """Build the search URL for a given engine."""
    encoded_q = quote_plus(query)
    if engine_name in SEARCH_PATTERNS:
        path = SEARCH_PATTERNS[engine_name].replace("{q}", encoded_q)
        return urljoin(base_url, path)
    return f"{base_url.rstrip('/')}/search/?q={encoded_q}"


# ---- Form-based search fallback ----

async def _try_form_search(page: Page, base_url: str, query: str) -> bool:
    """Load the engine homepage, find its search form, fill and submit it.
    Returns True if navigation to a results page succeeded."""
    try:
        success = await _navigate_with_retry(page, base_url)
        if not success:
            return False

        # Find a search input (try common selectors)
        search_input = None
        for selector in [
            'input[type="search"]', 'input[name="q"]', 'input[name="query"]',
            'input[name="search"]', 'input[name="keyword"]',
            'input[type="text"]',
        ]:
            search_input = await page.query_selector(selector)
            if search_input:
                break

        if not search_input:
            return False

        await search_input.fill(query)

        # Submit via button click if possible, else Enter key.
        # Use expect_navigation to properly wait for the new page.
        submit_btn = await page.query_selector(
            'input[type="submit"], button[type="submit"], button:not([type])')

        try:
            async with page.expect_navigation(timeout=90_000, wait_until="domcontentloaded"):
                if submit_btn:
                    await submit_btn.click()
                else:
                    await page.keyboard.press("Enter")
        except Exception:
            # Navigation may have already completed
            pass

        # Wait for JS-rendered results
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        return True
    except Exception:
        return False


# ---- Result cleaning ----

def _resolve_redirect_url(url: str) -> str:
    """Extract the actual destination from search engine redirect URLs.
    E.g. /search/redirect?redirect_url=http://actual.onion/path -> http://actual.onion/path"""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    for key in ("redirect_url", "url", "u", "q", "goto", "target", "link"):
        if key in params:
            candidate = params[key][0]
            if ".onion" in candidate:
                return candidate
    return url


def _clean_results(results: List[Dict], engine_host: str) -> List[Dict]:
    """Resolve redirect URLs and filter out self-referencing links."""
    cleaned = []
    for r in results:
        url = r.get("url", "")
        # Resolve redirects (e.g. Ahmia /search/redirect?redirect_url=...)
        resolved = _resolve_redirect_url(url)
        r["url"] = resolved
        # Filter self-references (engine linking to itself)
        if urlparse(resolved).netloc != engine_host:
            cleaned.append(r)
    return cleaned


# ---- Per-engine worker ----

async def _classify_and_extract(page: Page, engine_name: str,
                                 max_results: int) -> Tuple[List[Dict], str, str]:
    """Classify page and extract results. Shared by direct-URL and form-search paths."""
    page_type = await _detect_page_type(page)

    if page_type == "login":
        login_info = await _extract_login_page_info(page)
        return [], f"  - {engine_name}: login required ({login_info['notes']})", ""

    if page_type == "captcha":
        return [], f"  - {engine_name}: captcha-protected", ""

    if page_type == "error":
        error_info = await _extract_error_info(page)
        return [], "", f"  - {engine_name}: {error_info['error_text'][:100]}"

    if page_type == "directory":
        results = await _extract_directory_links(page, max_results)
        for r in results:
            r["source_engine"] = engine_name
            r["result_type"] = "directory_link"
        return results, "", ""

    if page_type == "search_results":
        results = await _parse_search_results(page, max_results)
        for r in results:
            r["source_engine"] = engine_name
            r["result_type"] = "search_result"
        return results, "", ""

    # "content" — could be actual results the classifier didn't recognize
    results = await _parse_search_results(page, max_results)
    for r in results:
        r["source_engine"] = engine_name
        r["result_type"] = "search_result"
    return results, "", ""


async def _query_engine(browser: Browser, engine_name: str, base_url: str,
                         query: str, max_results: int, semaphore: asyncio.Semaphore
                         ) -> Tuple[List[Dict], str, str]:
    """Query a single search engine. Returns (results, blocked_msg, error_msg)."""
    async with semaphore:
        page = await browser.new_page()
        try:
            # Attempt 1: direct search URL
            search_url = _build_search_url(engine_name, base_url, query)
            success = await _navigate_with_retry(page, search_url)

            if not success:
                return [], "", f"  - {engine_name}: unreachable after {MAX_RETRIES + 1} attempts"

            results, blocked, errored = await _classify_and_extract(page, engine_name, max_results)

            # Resolve redirect URLs and filter self-references
            engine_host = urlparse(base_url).netloc
            results = _clean_results(results, engine_host)

            # If direct URL returned no results and no blocking, try form-based search.
            # Engines with CSRF tokens or JS-only search need this.
            if not results and not blocked and not errored:
                form_ok = await _try_form_search(page, base_url, query)
                if form_ok:
                    results, blocked, errored = await _classify_and_extract(
                        page, engine_name, max_results)
                    results = _clean_results(results, engine_host)

            return results, blocked, errored

        except Exception as e:
            return [], "", f"  - {engine_name}: {str(e)[:100]}"
        finally:
            await page.close()


# ---- Result deduplication ----

def _normalize_url(url: str) -> str:
    """Normalize a URL for deduplication (strip trailing slash, fragment, lowercase)."""
    parsed = urlparse(url.lower())
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}{('?' + parsed.query) if parsed.query else ''}"


def _deduplicate_results(results: List[Dict]) -> List[Dict]:
    """Deduplicate results by URL. Merges source_engine into a list of sources."""
    seen = {}
    deduped = []
    for r in results:
        url = r.get("url", "")
        key = _normalize_url(url) if url else None

        if key and key in seen:
            # Merge this engine into the existing result's sources
            existing = seen[key]
            engine = r.get("source_engine", "")
            if engine and engine not in existing["source_engines"]:
                existing["source_engines"].append(engine)
            # Keep the longer description
            if len(r.get("description", "")) > len(existing.get("description", "")):
                existing["description"] = r["description"]
        else:
            # First occurrence — convert source_engine to a list
            entry = dict(r)
            engine = entry.pop("source_engine", "")
            entry["source_engines"] = [engine] if engine else []
            deduped.append(entry)
            if key:
                seen[key] = entry

    return deduped


# ---- Core async functions ----

async def _search_dark_web_async(query: str, max_results: int = 10) -> str:
    """Search all engines in parallel using Playwright."""
    async with async_playwright() as pw:
        browser = await _launch_tor_browser(pw)
        try:
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)

            tasks = [
                _query_engine(browser, name, url, query, max_results, semaphore)
                for name, url in SEARCH_URLS.items()
            ]

            results_list = await asyncio.gather(*tasks)

            raw_results = []
            blocked_sites = []
            errored_sites = []

            for results, blocked, errored in results_list:
                raw_results.extend(results)
                if blocked:
                    blocked_sites.append(blocked)
                if errored:
                    errored_sites.append(errored)

            # Deduplicate by URL, merging source engines
            all_results = _deduplicate_results(raw_results)

            # Build output
            output = f"Dark Web Search Results for: {query}\n"
            output += f"Engines queried: {len(SEARCH_URLS)} (max {MAX_CONCURRENT} parallel)\n"
            if len(all_results) != len(raw_results):
                output += f"Raw hits: {len(raw_results)}, unique after dedup: {len(all_results)}\n"
            output += "\n"

            if all_results:
                output += f"--- Results ({len(all_results)}) ---\n\n"
                for i, r in enumerate(all_results, 1):
                    output += f"{i}. {r['title']}\n"
                    output += f"   URL: {r['url']}\n"
                    sources = ", ".join(r.get("source_engines", []))
                    output += f"   Source: {sources}"
                    if r.get("result_type") == "directory_link":
                        output += " (directory listing)"
                    output += "\n"
                    if r.get("description"):
                        output += f"   {r['description']}\n"
                    output += "\n"
            else:
                output += "No results found across any accessible search engines.\n\n"

            if blocked_sites:
                output += f"--- Login/Captcha Blocked ({len(blocked_sites)}) ---\n"
                output += "\n".join(blocked_sites) + "\n\n"

            if errored_sites:
                output += f"--- Unreachable/Errors ({len(errored_sites)}) ---\n"
                output += "\n".join(errored_sites) + "\n"

            return output

        finally:
            await browser.close()


async def _browse_onion_async(url: str) -> str:
    """Browse a single .onion site using Playwright."""
    async with async_playwright() as pw:
        browser = await _launch_tor_browser(pw)
        try:
            page = await browser.new_page()
            try:
                success = await _navigate_with_retry(page, url)

                if not success:
                    return f"Error: Could not reach {url} after {MAX_RETRIES + 1} attempts"

                page_type = await _detect_page_type(page)
                title = await page.title() or "No title"

                if page_type == "login":
                    login_info = await _extract_login_page_info(page)
                    output = f"Page: {title}\nURL: {url}\nType: LOGIN PAGE\n\n"
                    output += f"This site requires authentication.\n"
                    output += f"{login_info['notes']}\n\n"
                    output += "Form fields:\n"
                    for f in login_info["fields"]:
                        output += f"  - {f['type']}: {f.get('name') or f.get('placeholder') or '(unnamed)'}\n"
                    return output

                if page_type == "captcha":
                    return (f"Page: {title}\nURL: {url}\nType: CAPTCHA PROTECTED\n\n"
                            f"This site requires captcha verification and cannot be accessed automatically.")

                if page_type == "error":
                    error_info = await _extract_error_info(page)
                    return (f"Page: {title}\nURL: {url}\nType: ERROR PAGE\n\n"
                            f"{error_info['error_text']}")

                if page_type == "directory":
                    links = await _extract_directory_links(page, max_links=30)
                    output = f"Page: {title}\nURL: {url}\nType: DIRECTORY ({len(links)} .onion links)\n\n"
                    for i, link in enumerate(links, 1):
                        output += f"{i}. {link['title']}\n   {link['url']}\n"
                        if link.get("description"):
                            output += f"   {link['description']}\n"
                        output += "\n"
                    return output

                # Regular content page
                text = await page.evaluate("() => document.body?.innerText || ''")
                text = text.strip()

                if len(text) > 5000:
                    text = text[:5000] + "\n\n... [truncated — page content exceeds 5000 characters]"

                return f"Page: {title}\nURL: {url}\nType: CONTENT\n\n{text}"

            finally:
                await page.close()
        finally:
            await browser.close()


# ---- Sync wrappers for Agno (handles running/non-running event loops) ----

def _run_async(coro):
    """Run an async coroutine, handling both sync and async calling contexts."""
    try:
        asyncio.get_running_loop()
        # Inside an async context (Agno) — run in a separate thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        # No running loop — safe to use asyncio.run()
        return asyncio.run(coro)


def search_dark_web(query: str, max_results: int = 10) -> str:
    """Search the dark web using Tor-based search engines for cyber threat intelligence.

    Queries multiple dark web search engines in parallel, handles login pages, captchas,
    error pages, and directory listings. Retries failed connections.

    Requires Tor to be running locally (default SOCKS5 proxy on 127.0.0.1:9050).

    Args:
        query: The search term or phrase to look for (e.g. "ransomware leak site",
               "credential dump", threat actor name, IOC).
        max_results: Maximum number of results to return per search engine (default 10).

    Returns:
        str: Formatted search results with titles, .onion URLs, and descriptions.
              Includes metadata about login-gated and captcha-protected sites.
    """
    try:
        return _run_async(_search_dark_web_async(query, max_results))
    except Exception as e:
        return f"Error performing dark web search: {str(e)}"


def browse_onion_site(url: str) -> str:
    """Browse a specific .onion site and return its page content as text.

    Automatically detects and reports login pages, captchas, and error pages
    instead of returning raw HTML. Retries on connection failure.

    Requires Tor to be running locally (default SOCKS5 proxy on 127.0.0.1:9050).

    Args:
        url: The full .onion URL to visit (e.g. "http://example.onion/page").

    Returns:
        str: The page title, type classification, and text content of the site.
    """
    try:
        return _run_async(_browse_onion_async(url))
    except Exception as e:
        return f"Error browsing {url}: {str(e)}"


def get_dark_web_search_tools():
    """Get dark web search tools as a list for use with Agno agents."""
    return [search_dark_web, browse_onion_site]
