import json,re,requests
from bs4 import BeautifulSoup
URL="https://www.posterterritory.com/poster-competitions/"
soup=BeautifulSoup(requests.get(URL,timeout=30,headers={"User-Agent":"Mozilla/5.0"}).text,"html.parser")
items=[]
months={"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06","july":"07","august":"08","september":"09","october":"10","november":"11","december":"12"}
heads=soup.find_all(["h2","h3","h4"])
for h in heads:
    title=h.get_text(" ",strip=True)
    if title in {"Poster Competitions","Design programs and Summer Schools","Open calls and platforms with no deadline"}: continue
    if not title or len(title)<3: continue
    text=""
    node=h
    for _ in range(8):
        node=node.find_next()
        if not node: break
        if getattr(node,"name",None) in ["h1","h2","h3","h4"] and node is not h: break
        text += " "+node.get_text(" ",strip=True)
    m=re.search(r"(?:Deadline|Last Deadline|New submission deadline)[:\s]+(?:\w+\s+)?(\d{1,2})[ ,]+(January|February|March|April|May|June|July|August|September|October|November|December)\s*,?\s*(2026)?",text,re.I)
    if not m:
        m=re.search(r"(?:Deadline|Last Deadline|New submission deadline)[:\s]+(\d{1,2})\s*(?:/|IX|X|VIII|VII)\s*2026",text,re.I)
    if m:
        if m.group(3): date=f"{m.group(3)}-{months[m.group(2).lower()]}-{int(m.group(1)):02d}"
        else: date=""
        if date: items.append({"title":title,"deadline":date,"resultDate":"","participating":False,"result":"pending"})
# fallback if theme structure changes: preserve any existing items rather than wiping the file
uniq={x["title"]:x for x in items}
if not uniq:
    raise SystemExit("No competitions parsed; refusing to overwrite competitions.json")
old=json.load(open("competitions.json",encoding="utf-8")) if __import__("os").path.exists("competitions.json") else []
oldmap={x["title"]:x for x in old}
for x in uniq.values():
    if x["title"] in oldmap:
        x["participating"]=oldmap[x["title"]].get("participating",False)
        x["result"]=oldmap[x["title"]].get("result","pending")
        x["resultDate"]=oldmap[x["title"]].get("resultDate","")
json.dump(list(uniq.values()),open("competitions.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)
print("Updated",len(uniq),"competitions")
