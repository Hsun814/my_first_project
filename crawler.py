import requests
import time
import csv
from bs4 import BeautifulSoup

# 把名言變成一個 list of dictionary
def parse_quotes(soup):
    results = []
    for q in soup.select("div.quote"):
        results.append({
            "text": q.select_one("span.text").get_text(),
            "author": q.select_one("small.author").get_text(),
            "tags": [t.get_text() for t in q.select("a.tag")]
        })
    return results

# url = "https://quotes.toscrape.com/"
# r = requests.get(url)
# print(r.status_code)
# print(r.encoding)

# quotes = parse_quotes(r.text)
# print(len(quotes))
# print(quotes[0])

all_quotes = []
url = "https://quotes.toscrape.com/"
while True:
    try:
        r = requests.get(url)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"{url} 失敗：{e}")
        break
    soup = BeautifulSoup(r.text, "html.parser")
    all_quotes.extend(parse_quotes(soup))
    time.sleep(1)

    next_btn = soup.select_one("li.next a")
    if next_btn is None:
        break
    url = "https://quotes.toscrape.com" + next_btn["href"]
    time.sleep(1)

print(len(all_quotes))

with open("quotes.csv", "w", newline="", encoding="utf-8-sig") as f:
     writer = csv.DictWriter(f, fieldnames=["text", "author","tags"])
     writer.writeheader()
     writer.writerows(all_quotes)

print(f"完成！！ {len(all_quotes)}則！")     