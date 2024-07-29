from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import urllib.parse
import time

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_MIMETYPE'] = 'application/json; charset=utf-8'

TIMEOUT = 10
MAX_SEARCH_TIME = 10
MAX_EXTRACT_TIME = 30

def get_page_content(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None

def decode_arabic(text):
    if isinstance(text, str):
        try:
            return text.encode('utf-8').decode('utf-8')
        except Exception:
            return text
    return text

def scrape_episode_urls(content):
    soup = BeautifulSoup(content, 'html.parser')
    episodes_list = soup.find('div', id='DivEpisodesList')
    if not episodes_list:
        return []
    episode_containers = episodes_list.find_all('div', class_='DivEpisodeContainer')
    return [(decode_arabic(link.text.strip()), link['href']) for container in episode_containers if (link := container.find('a')) and 'href' in link.attrs]

def scrape_episode_servers(url):
    content = get_page_content(url)
    if not content:
        return []
    soup = BeautifulSoup(content, 'html.parser')
    hardsub_content = soup.find('div', class_='hardsub-content')
    if not hardsub_content:
        return []
    servers = hardsub_content.find_all('li')
    return [{'name': decode_arabic(link.text.strip()), 'url': link['data-ep-url']} 
            for server in servers if (link := server.find('a')) and 'data-ep-url' in link.attrs]

def scrape_anime_cards(content):
    soup = BeautifulSoup(content, 'html.parser')
    anime_list_content = soup.find('div', class_='anime-list-content')
    if not anime_list_content:
        return []
    anime_cards = anime_list_content.find_all('div', class_='anime-card-container')
    results = []
    for card in anime_cards:
        poster_div = card.find('div', class_='anime-card-poster')
        details_div = card.find('div', class_='anime-card-details')
        if poster_div and details_div:
            image = poster_div.find('img', class_='img-responsive')
            ani_url = poster_div.find('a', class_='overlay')
            type_div = details_div.find('div', class_='anime-card-type')
            title_div = details_div.find('div', class_='anime-card-title')
            result = {
                "image_url": image['src'] if image and 'src' in image.attrs else None,
                "ani_url": ani_url['href'] if ani_url and 'href' in ani_url.attrs else None,
                "type": decode_arabic(type_div.text.strip()) if type_div else None,
                "title": decode_arabic(title_div.find('h3').text.strip()) if title_div and title_div.find('h3') else None,
            }
            results.append(result)
    return results

def scrape_all_pages(base_url):
    all_results = []
    page = 1
    start_time = time.time()
    
    while time.time() - start_time < MAX_SEARCH_TIME:
        url = f"{base_url}&page={page}" if page > 1 else base_url
        content = get_page_content(url)
        if not content:
            break
        results = scrape_anime_cards(content)
        if not results:
            break
        all_results.extend(results)
        page += 1
        
        if time.time() - start_time > MAX_SEARCH_TIME * 0.8:
            print(f"Approaching time limit. Scraped {page} pages.")
            break

    print(f"Scraped {page} pages in {time.time() - start_time:.2f} seconds")
    return all_results

def process_all_episodes(episodes):
    results = []
    start_time = time.time()
    for episode in episodes:
        if time.time() - start_time > MAX_EXTRACT_TIME:
            print(f"Reached time limit. Processed {len(results)} out of {len(episodes)} episodes.")
            break
        name, url = episode
        servers = scrape_episode_servers(url)
        results.append({'episode_name': name, 'servers': servers})
    return results

@app.route('/api/search', methods=['GET'])
def api_search_anime():
    query = request.args.get('q', '')
    if not query:
        return jsonify({"error": "No search query provided"}), 400
    
    formatted_query = urllib.parse.quote_plus(query)
    search_url = f"https://www.octanime.tv/search/?s={formatted_query}"
    
    results = scrape_all_pages(search_url)
    
    response = jsonify({
        "results": results,
        "total_results": len(results),
        "search_query": query
    })
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route('/api/extract', methods=['GET'])
def api_extract_episodes():
    url = request.args.get('url', '')
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    content = get_page_content(url)
    if not content:
        return jsonify({"error": f"Failed to fetch the page: {url}"}), 500
    
    episodes = scrape_episode_urls(content)
    if not episodes:
        return jsonify({"error": "No episodes found on the page"}), 404
    
    results = process_all_episodes(episodes)
    
    response = jsonify({
        "total_episodes": len(episodes),
        "processed_episodes": len(results),
        "results": results
    })
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

if __name__ == '__main__':
    app.run(debug=True)