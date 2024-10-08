import os
from dotenv import load_dotenv
import requests
from urllib.parse import quote_plus
import re
import base64

# Load environment variables from .env file
load_dotenv()

# Get API keys and settings from environment variables
URLSCAN_API_KEY = os.getenv('URLSCAN_API_KEY')
BING_API_KEY = os.getenv('BING_API_KEY')
FOFA_API_KEY = os.getenv('FOFA_API_KEY')
CENSYS_API_KEY = os.getenv('CENSYS_API_KEY')
SHODAN_API_KEY = os.getenv('SHODAN_API_KEY')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_SEARCH_ENGINE_ID = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
RESULT_LIMIT = int(os.getenv('RESULT_LIMIT', 100))

def get_domains_from_urlscan(query):
    url = 'https://urlscan.io/api/v1/search/'
    headers = {'API-Key': URLSCAN_API_KEY}
    params = {'q': query, 'size': RESULT_LIMIT}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    results = response.json().get('results', [])
    return [result['page']['domain'] for result in results]

def get_ips_from_fofa(query):
    if ':' not in FOFA_API_KEY:
        print("Error: FOFA API key is not in the correct format. It should be 'email:key'.")
        return []

    email, key = FOFA_API_KEY.split(':', 1)
    query_base64 = base64.b64encode(query.encode()).decode()
    url = f'https://fofa.info/api/v1/search/all?email={email}&key={key}&qbase64={query_base64}&size={RESULT_LIMIT}&fields=ip,host'
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        results = response.json()
        if results.get('error'):
            if results.get('errmsg') == '[820031] F点余额不足':
                print("Error: Insufficient FOFA credits (F-points) to perform the search.")
            elif results.get('errmsg') == '[820000] 查询语法错误':
                print("Error: Query syntax error. Please check your FOFA query syntax.")
                print("FOFA query syntax guide: https://en.fofa.info/api")
            else:
                print(f"FOFA API error: {results['errmsg']}")
            return []
        return [result[0] if result[0] else result[1] for result in results.get('results', [])]
    except requests.exceptions.RequestException as e:
        print(f"Error querying FOFA: {e}")
        return []
    except (KeyError, IndexError) as e:
        print(f"Error parsing FOFA results: {e}")
        return []

def get_ips_from_censys(query):
    url = 'https://search.censys.io/api/v2/hosts/search'
    # Ensure CENSYS_API_KEY is in the correct format (API ID:API Secret)
    if ':' not in CENSYS_API_KEY:
        print("Error: Censys API key is not in the correct format. It should be 'API ID:API Secret'.")
        return []
    
    api_id, api_secret = CENSYS_API_KEY.split(':', 1)
    auth = (api_id, api_secret)
    headers = {'Accept': 'application/json'}
    params = {'q': query, 'per_page': RESULT_LIMIT}
    
    try:
        response = requests.get(url, auth=auth, headers=headers, params=params)
        response.raise_for_status()
        results = response.json().get('result', {}).get('hits', [])
        return [result.get('ip') for result in results]
    except requests.exceptions.HTTPError as e:
        print(f"Censys API error: {e}")
        print(f"Response content: {response.text}")
        return []
    except Exception as e:
        print(f"Error querying Censys: {e}")
        return []

def get_ips_from_shodan(query):
    api_key = os.getenv('SHODAN_API_KEY')
    base_url = "https://api.shodan.io/shodan/host/search"
    params = {
        'key': api_key,
        'query': query,
        'limit': int(os.getenv('RESULT_LIMIT', 100))
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        return [result['ip_str'] for result in data.get('matches', [])]
    except requests.exceptions.HTTPError as e:
        print(f"Shodan API error: {e}")
        print(f"Response content: {response.text}")
        return []
    except Exception as e:
        print(f"Error querying Shodan: {e}")
        return []

def search_articles_for_domains(domains_or_ips, engine='bing'):
    search_results = {}
    for item in domains_or_ips:
        query = quote_plus(f'"{item}"')
        if engine == 'bing':
            search_url = f'https://api.bing.microsoft.com/v7.0/search?q={query}'
            headers = {'Ocp-Apim-Subscription-Key': BING_API_KEY}
        else:  # Google
            search_url = f'https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_KEY}&cx={GOOGLE_SEARCH_ENGINE_ID}&q={query}'
            headers = {}
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        search_results[item] = response.json()
    return search_results

def parse_search_results(search_results, engine='bing'):
    parsed_results = {}
    for item, results in search_results.items():
        articles = []
        if engine == 'bing':
            items = results.get('webPages', {}).get('value', [])
        else:  # Google
            items = results.get('items', [])
        
        for result in items:
            article_url = result.get('url' if engine == 'bing' else 'link')
            if article_url:
                try:
                    article_domain = re.search(r'https?://([^/]+)', article_url).group(1)
                    if article_domain != item:
                        title = result.get('name' if engine == 'bing' else 'title')
                        snippet = result.get('snippet')
                        articles.append({'title': title, 'snippet': snippet, 'url': article_url})
                except AttributeError:
                    print(f"Warning: Unable to parse URL: {article_url}")
            else:
                print(f"Warning: No URL found for result: {result}")
        parsed_results[item] = articles
    return parsed_results

def check_item_in_text(item, text):
    escaped_item = re.escape(item)
    patterns = [
        escaped_item,
        escaped_item.replace(r'\.', r'\[dot\]'),
        escaped_item.replace(r'\.', r'\(dot\)'),
        escaped_item.replace(r'\.', r'\s*\.\s*')
    ]
    combined_pattern = '|'.join(patterns)
    try:
        return re.search(combined_pattern, text, re.IGNORECASE) is not None
    except re.error as e:
        print(f"Regex error: {e}")
        return False

def save_results_to_file(parsed_results, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        for item, articles in parsed_results.items():
            f.write(f"Articles found for {item}:\n")
            f.write("=" * 80 + "\n")
            for article in articles:
                if check_item_in_text(item, article['snippet']):
                    f.write(f"Title  : {article['title']}\n")
                    f.write(f"Snippet: {article['snippet']}\n")
                    f.write(f"URL    : {article['url']}\n")
                    f.write("-" * 80 + "\n")
            f.write("\n")

def get_direct_input():
    input_str = input("Enter domains/IPs (comma-separated): ")
    return [item.strip() for item in input_str.split(',')]

def get_results_from_api(source, query):
    if source == 'u':
        return get_domains_from_urlscan(query)
    elif source == 'f':
        return get_ips_from_fofa(query)
    elif source == 'c':
        return get_ips_from_censys(query)
    elif source == 's':
        return get_ips_from_shodan(query)

def main():
    print("Select search source:")
    print("[u] URLScan\n[f] FOFA\n[c] Censys\n[s] Shodan\n[d] Direct Input (domains/IPs)")
    source_choice = input("Enter your choice (u/f/c/s/d): ").lower()

    if source_choice in ['u', 'f', 'c', 's']:
        query = input("Enter your search query: ")
        domains_or_ips = get_results_from_api(source_choice, query)
    elif source_choice == 'd':
        domains_or_ips = get_direct_input()
    else:
        print("Invalid choice. Exiting.")
        return

    print("\nSelect search engine for articles:")
    print("[b] Bing\n[g] Google")
    engine_choice = input("Enter your choice (b/g): ").lower()
    engine = 'bing' if engine_choice == 'b' else 'google'

    search_results = search_articles_for_domains(domains_or_ips, engine)
    parsed_results = parse_search_results(search_results, engine)
    
    for item, articles in parsed_results.items():
        print(f"Articles found for {item}:")
        print("=" * 80)
        for article in articles:
            if check_item_in_text(item, article['snippet']):
                print(f"Title  : {article['title']}")
                print(f"Snippet: {article['snippet']}")
                print(f"URL    : {article['url']}")
                print("-" * 80)
        print("\n")
    
    save_option = input("Do you want to save the results to a file? (y/n): ").lower()
    if save_option == 'y':
        filename = input("Enter the filename to save results (e.g., results.txt): ")
        save_results_to_file(parsed_results, filename)
        print(f"Results saved to {filename}")

if __name__ == "__main__":
    main()