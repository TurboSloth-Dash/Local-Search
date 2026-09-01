
from __future__ import annotations
import re, sqlite3, datetime as dt
from pathlib import Path
import requests
from rapidfuzz import fuzz

LOC_BASE = "https://www.loc.gov/collections/chronicling-america/"
HEADERS = {"User-Agent":"GulfSouthForgottenHistory/6.0 historical research"}

# Free Library of Congress newspaper targets that fit the regional-history mission.
NEWSPAPERS = {
    "St. Tammany Farmer": {"lccn":"sn82015387","area":"St. Tammany Parish, Louisiana","years":"1874-current"},
    "Sea Coast Echo": {"lccn":"sn86074033","area":"Bay St. Louis / Mississippi Gulf Coast","years":"1892-current"},
    "Free Press": {"lccn":"sn87065567","area":"Poplarville / Pearl River County, Mississippi","years":"1890s-1920s"},
    "Era-Leader": {"lccn":"sn88064305","area":"Franklinton / Washington Parish, Louisiana","years":"1910-current"},
    "Bogalusa Enterprise": {"lccn":"sn88064054","area":"Bogalusa, Louisiana","years":"1914-1918"},
    "Bogalusa Enterprise and American": {"lccn":"sn88064055","area":"Bogalusa, Louisiana","years":"1918+"},
    "New Orleans Democrat": {"lccn":"sn88064616","area":"New Orleans, Louisiana","years":"1875-1876"},
    "Times-Democrat": {"lccn":"sn83016709","area":"New Orleans, Louisiana","years":"1881-1914"},
}

SOURCE_REGISTRY = [
    {"family":"Newspapers","source":"Library of Congress Chronicling America","area":"Louisiana / Gulf South","access":"Automatic","cost":"Free","purpose":"OCR-searchable historical newspapers"},
    {"family":"Archives","source":"Historic New Orleans Collection","area":"New Orleans / Louisiana","access":"Open & search","cost":"Free public material","purpose":"manuscripts, maps, photographs, property and archival collections"},
    {"family":"Archives","source":"Louisiana Digital Library / LSU","area":"Louisiana","access":"Open & search","cost":"Free public material","purpose":"newspapers, photographs, manuscripts and digital collections"},
    {"family":"Archives","source":"Tulane digital collections","area":"New Orleans / Louisiana","access":"Open & search","cost":"Free public material","purpose":"archives, maps, newspapers and manuscripts"},
    {"family":"Genealogy","source":"U.S. Census / National Archives","area":"United States","access":"Open & search","cost":"Free","purpose":"households, age, occupation, birthplace and residence"},
    {"family":"Genealogy","source":"FamilySearch public collections","area":"Louisiana / Gulf South","access":"Open & search","cost":"Free account may be needed","purpose":"voter, vital, cemetery, passenger and family records"},
    {"family":"Business","source":"Louisiana Secretary of State Commercial Search","area":"Louisiana","access":"Open & search","cost":"Free","purpose":"business identity, officers, agents and status"},
    {"family":"Business","source":"Louisiana licensing boards / contractor lookup","area":"Louisiana","access":"Open & search","cost":"Free","purpose":"licenses, contractors and professional records"},
    {"family":"Government","source":"Louisiana Ethics Administration","area":"Louisiana","access":"Open & search","cost":"Free","purpose":"campaign finance, ethics, lobbying and disclosures"},
    {"family":"Government","source":"Louisiana Legislative Auditor","area":"Louisiana","access":"Open & search","cost":"Free","purpose":"audits, findings and public finances"},
    {"family":"Government","source":"Louisiana procurement / LaPAC","area":"Louisiana","access":"Open & search","cost":"Free","purpose":"bids, vendors, awards and contracts"},
    {"family":"Government","source":"Local parish and municipal portals","area":"Southeast Louisiana","access":"Open & search","cost":"Free","purpose":"budgets, annual reports, agendas, minutes, contracts and ordinances"},
    {"family":"Government","source":"USASpending.gov / SAM.gov","area":"Federal","access":"Open & search","cost":"Free","purpose":"federal awards, grants, vendors and contracts"},
]

ABBR = {
    "william":"wm","charles":"chas","robert":"robt","james":"jas","joseph":"jos",
    "thomas":"thos","george":"geo","henry":"hy","john":"jno","samuel":"saml",
    "benjamin":"benj","frederick":"fredk","alexander":"alexr","richard":"richd"
}
OCR_SWAPS=[("m","rn"),("rn","m"),("l","1"),("i","1"),("o","0"),("c","e"),("e","c"),("w","vv")]

HISTORICAL_TERMS = {
    "business closed":["closed","retired from business","dissolution","dissolved partnership","stock for sale","removed to","assignment","receiver"],
    "moved":["moved","removed to","formerly of","changed residence","located at","removed from"],
    "business started":["opened","established","new firm","new business","incorporated","partnership","commenced business"],
    "death":["died","death","obituary","funeral","interment","buried","succession","estate"],
    "property":["sold","sale","conveyance","mortgage","sheriff sale","tax sale","property","lot"],
    "brand":["brand","trade mark","trademark","manufactured by","manufactured for","sole agents","dealers in"],
    "contract":["contract","bid","proposal","award","vendor","purchase order","change order","appropriation"],
}

DB_PATH = Path("data/research_cache.db")
DB_PATH.parent.mkdir(exist_ok=True)
SCHEMA = """
CREATE TABLE IF NOT EXISTS pages(
 id TEXT PRIMARY KEY, newspaper TEXT, lccn TEXT, date TEXT, year INTEGER, title TEXT,
 url TEXT, image_url TEXT, full_text TEXT, corrected_text TEXT DEFAULT '',
 verified_text TEXT DEFAULT '', page_number INTEGER DEFAULT 0
);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
 id UNINDEXED, full_text, corrected_text, verified_text,
 tokenize='unicode61 remove_diacritics 2'
);
"""

def con():
    c=sqlite3.connect(DB_PATH)
    c.row_factory=sqlite3.Row
    return c

def init_db():
    with con() as c:
        c.executescript(SCHEMA)

def clean(s):
    return re.sub(r"\s+"," ",(s or "").strip())

def infer_subject_type(query):
    q=(query or "").lower()
    if any(x in q for x in ["street","road","avenue","building","house","property","lot ","address"]):
        return "Place"
    if any(x in q for x in ["company"," co "," corp","llc","l.l.c","business","store","factory","bank","association","lodge","club","church","school","brothers","bros"]):
        return "Business / Organization"
    return "Person / Subject"

def period_terms(question):
    q=(question or "").lower()
    terms=[]
    for concept, words in HISTORICAL_TERMS.items():
        if concept in q or any(w in q for w in words[:2]):
            terms.extend(words)
    return list(dict.fromkeys(terms))[:12]

def variants(q):
    q=clean(q)
    if not q:
        return []
    out=[q,q.replace(".",""),q.replace("-"," ")]
    w=q.split()
    if 2<=len(w)<=5:
        first,last=w[0],w[-1]
        mid=w[1:-1]
        out.append(f"{first} {last}")
        if mid:
            out += [f"{first} {mid[0][0]} {last}", f"{first[0]} {' '.join(mid)} {last}"]
        ab=ABBR.get(first.lower().rstrip("."))
        if ab:
            out.append(f"{ab} {last}")
    # Historical spelling / punctuation variants.
    out += [
        q.replace("Saint ","St. "),
        q.replace("St. ","Saint "),
        q.replace("Brothers","Bros."),
        q.replace("Bros.","Brothers"),
        q.replace("Company","Co."),
        q.replace("Co.","Company"),
    ]
    for a,b in OCR_SWAPS:
        if a in q.lower():
            out.append(re.sub(a,b,q,count=1,flags=re.I))
    seen=[]
    for x in out:
        x=clean(x)
        if x and x.lower() not in [s.lower() for s in seen]:
            seen.append(x)
    return seen[:20]

def newspaper_targets(location="", mode="Standard"):
    loc=(location or "").lower()
    picks=["St. Tammany Farmer"]
    if any(x in loc for x in ["bay st","bay saint","waveland","hancock","mississippi gulf","pearlington"]):
        picks.insert(0,"Sea Coast Echo")
    if any(x in loc for x in ["poplarville","pearl river","picayune"]):
        picks.insert(0,"Free Press")
    if any(x in loc for x in ["franklinton","washington parish"]):
        picks.insert(0,"Era-Leader")
    if any(x in loc for x in ["bogalusa"]):
        picks = ["Bogalusa Enterprise","Bogalusa Enterprise and American","Era-Leader"] + picks
    if any(x in loc for x in ["new orleans","orleans"]):
        picks = ["Times-Democrat","New Orleans Democrat","St. Tammany Farmer"] + picks
    if mode=="Deep":
        picks += ["Sea Coast Echo","Era-Leader","Times-Democrat","Free Press"]
    return list(dict.fromkeys(picks))[:6]

def loc_search(query,start_year,end_year,lccn,count=30,operation="AND",page=1):
    params={
        "dl":"page","qs":query,"ops":operation,"fa":f"number_lccn:{lccn}",
        "start_date":f"{start_year}-01-01","end_date":f"{end_year}-12-31",
        "fo":"json","c":min(count,100),"sp":page,"at":"pagination,results"
    }
    r=requests.get(LOC_BASE,params=params,headers=HEADERS,timeout=35)
    r.raise_for_status()
    return r.json()

def norm(raw,newspaper,lccn):
    item=raw.get("item") or {}
    rid=raw.get("id") or raw.get("url") or item.get("id") or item.get("url") or ""
    date=raw.get("date") or item.get("date") or ""
    if isinstance(date,list): date=date[0] if date else ""
    y=int(str(date)[:4]) if str(date)[:4].isdigit() else None
    title=raw.get("title") or item.get("title") or newspaper
    text=raw.get("full_text") or item.get("full_text") or ""
    image=raw.get("image_url") or item.get("image_url") or ""
    if isinstance(image,list): image=image[0] if image else ""
    pn=0
    m=re.search(r"[?&]sp=(\d+)",rid)
    if m: pn=int(m.group(1))
    return {"id":rid,"newspaper":newspaper,"lccn":lccn,"date":str(date),"year":y,
            "title":str(title),"url":rid,"image_url":image if isinstance(image,str) else "",
            "full_text":text if isinstance(text,str) else "","page_number":pn}

def upsert_page(p):
    with con() as c:
        c.execute("""insert into pages(id,newspaper,lccn,date,year,title,url,image_url,full_text,page_number)
                     values(?,?,?,?,?,?,?,?,?,?)
                     on conflict(id) do update set newspaper=excluded.newspaper,lccn=excluded.lccn,
                     date=excluded.date,year=excluded.year,title=excluded.title,url=excluded.url,
                     image_url=excluded.image_url,full_text=excluded.full_text,page_number=excluded.page_number""",
                  (p["id"],p["newspaper"],p["lccn"],p["date"],p["year"],p["title"],p["url"],
                   p["image_url"],p["full_text"],p["page_number"]))
        row=c.execute("select * from pages where id=?",(p["id"],)).fetchone()
        c.execute("delete from pages_fts where id=?",(p["id"],))
        c.execute("insert into pages_fts(id,full_text,corrected_text,verified_text) values(?,?,?,?)",
                  (p["id"],row["full_text"],row["corrected_text"],row["verified_text"]))

def update_text(page_id, corrected=None, verified=None):
    with con() as c:
        row=c.execute("select * from pages where id=?",(page_id,)).fetchone()
        if not row: return
        corrected=row["corrected_text"] if corrected is None else corrected
        verified=row["verified_text"] if verified is None else verified
        c.execute("update pages set corrected_text=?,verified_text=? where id=?",(corrected,verified,page_id))
        c.execute("delete from pages_fts where id=?",(page_id,))
        c.execute("insert into pages_fts(id,full_text,corrected_text,verified_text) values(?,?,?,?)",
                  (page_id,row["full_text"],corrected,verified))

def get_page(page_id):
    with con() as c:
        r=c.execute("select * from pages where id=?",(page_id,)).fetchone()
        return dict(r) if r else None

def score(text,q,context):
    t=(text or "").lower(); ql=(q or "").lower()
    s=0; why=[]
    if ql and ql in t:
        s+=55; why.append("exact phrase")
    else:
        f=fuzz.partial_ratio(ql,t[:18000]) if ql else 0
        if f>=65:
            s+=min(38,f*.38); why.append(f"OCR/fuzzy {f:.0f}%")
    ctx=[clean(x).lower() for x in re.split(r"[,;\n]+",context or "") if clean(x)]
    hits=sum(1 for x in ctx if x in t)
    if hits:
        s+=min(30,hits*10); why.append(f"{hits} context hit(s)")
    return round(min(100,s),1),why

def snip(text,q,context,radius=300):
    text=text or ""; low=text.lower()
    terms=[q]+[clean(x) for x in re.split(r"[,;\n]+",context or "") if clean(x)]
    pos=[low.find(x.lower()) for x in terms if x and low.find(x.lower())>=0]
    i=min(pos) if pos else 0
    a=max(0,i-radius); b=min(len(text),i+radius)
    s=clean(text[a:b])
    return ("..." if a else "")+s+("..." if b<len(text) else "")

def cluster_key(result):
    # Intentionally coarse: duplicate/near-duplicate hits collapse by date + normalized first words.
    txt=re.sub(r"\W+"," ",(result.get("snippet") or "").lower())
    words=[w for w in txt.split() if len(w)>3][:18]
    return (result.get("newspaper",""), result.get("date",""), " ".join(words[:8]))

def progressive_search(query,location,start,end,depth="Standard",question="",limit=60,already_searched=None):
    """Smart but bounded search: variants + historical terms + only relevant regional papers."""
    already_searched=set(already_searched or [])
    context=", ".join([x for x in [location,question] if x])
    targets=newspaper_targets(location,depth)
    terms=[(query,"PHRASE")]
    if len(query.split())>1: terms.append((query,"~10"))
    for v in variants(query)[1:6]:
        terms.append((v,"PHRASE" if " " in v else "AND"))
    for h in period_terms(question)[:5]:
        terms.append((f"{query} {h}","~10"))
    # Keep searches bounded.
    per_paper = 3 if depth=="Quick" else 6 if depth=="Standard" else 9
    found={}
    search_log=[]
    for paper in targets:
        lccn=NEWSPAPERS[paper]["lccn"]
        for term,op in terms[:per_paper]:
            sig=f"{paper}|{term}|{op}|{start}|{end}"
            if sig in already_searched:
                continue
            try:
                data=loc_search(term,start,end,lccn,count=25,operation=op)
                count=0
                for raw in data.get("results",[]):
                    p=norm(raw,paper,lccn)
                    if not p["id"]: continue
                    found.setdefault(p["id"],p|{"queries":[]})
                    found[p["id"]]["queries"].append(f"{op}: {term}")
                    if p["full_text"]: upsert_page(p)
                    count+=1
                search_log.append({"signature":sig,"source":paper,"query":term,"status":f"{count} page hit(s)"})
            except Exception as e:
                search_log.append({"signature":sig,"source":paper,"query":term,"status":"temporarily unavailable"})
    out=[]
    for p in found.values():
        sc,why=score(p["full_text"],query,context)
        out.append(p|{"score":sc,"why":why,"snippet":snip(p["full_text"],query,context),"text_source":"LOC OCR"})
    out=sorted(out,key=lambda x:(-x["score"],x["date"]))[:limit]

    # Duplicate suppression with a visible count.
    clustered={}
    for r in out:
        k=cluster_key(r)
        if k not in clustered:
            clustered[k]=r|{"similar_count":1}
        else:
            clustered[k]["similar_count"]+=1
    return list(clustered.values()), search_log

ORG_WORDS=r"(Company|Co\.?|Corporation|Corp\.?|Association|Assn\.?|Bank|Store|Mercantile|Brothers|Bros\.?|Lodge|Council|Club|Church|School|Factory|Works|Hotel|Railroad|Railway|Plantation|Society)"
ADDRESS_END=r"(?:Street|St\.|Avenue|Ave\.|Road|Rd\.|Boulevard|Blvd\.|Lane|Ln\.|Highway|Hwy\.|Square|Place|Pl\.)"

def extract_entities(text):
    text=text or ""
    people=set(re.findall(r"\b(?:Mr\.|Mrs\.|Miss|Dr\.|Capt\.|Col\.|Judge|Rev\.)?\s*([A-Z][a-z]{2,}\s+(?:[A-Z]\.?\s+)?[A-Z][a-z]{2,})\b",text))
    orgs=set()
    for m in re.finditer(rf"\b([A-Z][A-Za-z0-9.&'\- ]{{2,70}}\s+{ORG_WORDS})\b",text):
        orgs.add(clean(m.group(1)))
    addresses=set(re.findall(rf"\b\d{{1,5}}\s+[A-Z][A-Za-z.'\- ]{{2,40}}\s{ADDRESS_END}\b",text))
    money=set(re.findall(r"\$\s?\d[\d,]*(?:\.\d{2})?",text))
    identifiers=set(re.findall(r"\b(?:Contract|Project|Ordinance|Resolution|Bid|RFP|No\.)\s*[#:]?\s*[A-Z0-9\-]{3,20}\b",text,re.I))
    return {
        "people":sorted(people)[:30],
        "organizations":sorted(orgs)[:30],
        "addresses":sorted(addresses)[:25],
        "money":sorted(money)[:20],
        "identifiers":sorted(identifiers)[:20],
    }

def entity_type(name):
    n=(name or "").lower()
    if re.match(r"^\d+\s+",n): return "Address"
    if re.search(ORG_WORDS,n,re.I): return "Business / Organization"
    if n.startswith("$"): return "Amount"
    if any(k in n for k in ["contract","project","ordinance","resolution","rfp","bid"]): return "Record Identifier"
    return "Person"

def add_result_to_case(case,r):
    if not any(x.get("id")==r.get("id") for x in case["results"]):
        item={k:r.get(k) for k in ["id","date","year","newspaper","title","url","image_url","page_number","score","snippet","text_source"]}
        item["verification"]="Needs review"
        case["results"].append(item)
    p=get_page(r["id"])
    ents=extract_entities((p or {}).get("full_text") or r.get("snippet",""))
    all_entities=ents["people"]+ents["organizations"]+ents["addresses"]+ents["identifiers"]
    existing={(e["type"],e["name"].lower()) for e in case["entities"]}
    for n in all_entities:
        et=entity_type(n)
        if (et,n.lower()) not in existing:
            case["entities"].append({
                "type":et,"name":n,"context":f"Found in {r.get('newspaper') or r.get('title')}",
                "source":r.get("url",""),"confidence":"Lead"
            })
    if r.get("date"):
        case["events"].append({"date":r["date"],"event":r.get("snippet","")[:260],
                               "source_id":r["id"],"source":r.get("newspaper",""),"url":r.get("url","")})

def existing_case_terms(case):
    vals=[]
    for e in case.get("entities",[]):
        vals.append(e.get("name",""))
    return {clean(v).lower() for v in vals if clean(v)}

def new_information(result,case):
    ents=extract_entities(result.get("snippet",""))
    known=existing_case_terms(case)
    fresh=[]
    for bucket in ["people","organizations","addresses","identifiers"]:
        for x in ents[bucket]:
            if x.lower() not in known:
                fresh.append(x)
    return fresh[:8]

def lead_priority(name,case,subject_type):
    et=entity_type(name)
    points=50
    reason=[]
    if et=="Business / Organization":
        points+=20; reason.append("organization can unlock officers, addresses and records")
    if et=="Address":
        points+=18; reason.append("address can connect people, businesses and property")
    if et=="Record Identifier":
        points+=25; reason.append("exact identifier can unlock precise records")
    if et=="Person":
        points+=10; reason.append("person may reveal family or business relationships")
    if name.lower() in existing_case_terms(case):
        points-=30; reason.append("already known")
    return max(0,min(100,points)), "; ".join(reason)

def best_followups(result,case,subject_type="Person / Subject"):
    ents=extract_entities(result.get("snippet",""))
    items=ents["organizations"]+ents["addresses"]+ents["identifiers"]+ents["people"]
    scored=[]
    for n in list(dict.fromkeys(items)):
        score_,why=lead_priority(n,case,subject_type)
        if score_>=45:
            scored.append({"lead":n,"type":entity_type(n),"priority":score_,"why":why})
    return sorted(scored,key=lambda x:-x["priority"])[:8]

def business_source_plan(name,period_end=2026):
    historical = period_end < 1950
    if historical:
        return [
            "Historical newspapers and advertisements",
            "City/business directories",
            "Property / conveyance / mortgage records",
            "Historic maps and photographs",
            "Incorporation / legal notices",
            "LSU, Tulane, HNOC and Louisiana Digital Library collections",
        ]
    return [
        "Louisiana Secretary of State commercial records",
        "Licensing / contractor databases when applicable",
        "Property and address records",
        "Local procurement, contracts, agendas and budgets",
        "Louisiana Legislative Auditor",
        "Campaign finance / ethics only when relevant",
        "USASpending / SAM for federal awards",
        "News and archived newspapers for context",
    ]

def research_gaps(case):
    gaps=[]
    results=case.get("results",[])
    entities=case.get("entities",[])
    if not results:
        return ["No evidence has been saved yet."]
    types={e.get("type") for e in entities}
    if "Address" not in types:
        gaps.append("No address has been established. An address can connect people, businesses and property.")
    if "Business / Organization" not in types:
        gaps.append("No business or organization has been established. Check advertisements, directories and legal notices if relevant.")
    years=sorted({r.get("year") for r in results if isinstance(r.get("year"),int)})
    if len(years)>=2 and years[-1]-years[0]>=5:
        gaps.append(f"Evidence spans {years[0]}-{years[-1]}. Look for unexplained changes or gaps inside that period.")
    if all((r.get("verification") or "")=="Needs review" for r in results):
        gaps.append("No saved finding is marked verified or corroborated yet.")
    if not case.get("negative_searches"):
        gaps.append("No negative-search log exists yet. Recording unsuccessful searches helps prevent repeating weak branches.")
    if not gaps:
        gaps.append("Core evidence coverage looks reasonable. Focus next on contradictions, first/last appearances and unanswered questions.")
    return gaps

def source_recommendations(subject_type,year_end,question=""):
    q=(question or "").lower()
    rec=[]
    if subject_type=="Business / Organization":
        rec.extend(business_source_plan("",year_end))
    elif subject_type=="Place":
        rec.extend(["Historical newspapers","Property / conveyance records","Historic maps","City directories","Photograph and archive collections"])
    else:
        rec.extend(["Historical newspapers","Census / voter / vital records","Directories","Obituaries / cemetery records","Property / business records when discovered"])
    if any(x in q for x in ["contract","budget","government","council","audit","politic","election"]):
        rec += ["Local government agendas/minutes/budgets","Louisiana procurement","Louisiana Legislative Auditor","Louisiana Ethics / election records when relevant"]
    return list(dict.fromkeys(rec))

def fresh_case():
    return {
        "case_name":"","research_id":"","subject":"","subject_type":"Person / Subject","location":"",
        "start_year":1874,"end_year":1922,"question":"","depth":"Standard","notes":"",
        "results":[],"entities":[],"events":[],"search_log":[],"negative_searches":[],
        "questions":[],"hypotheses":[]
    }
