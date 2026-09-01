
from __future__ import annotations
import json, re
import pandas as pd
import streamlit as st
from pyvis.network import Network
import streamlit.components.v1 as components

from research_core import (
    init_db, progressive_search, add_result_to_case, get_page, update_text, extract_entities,
    best_followups, infer_subject_type, source_recommendations, business_source_plan,
    research_gaps, fresh_case, SOURCE_REGISTRY, NEWSPAPERS
)
from reports import make_pdf, make_excel

st.set_page_config(page_title="Gulf South Forgotten History",page_icon="🧭",layout="wide")

st.markdown("""
<style>
.block-container {max-width: 1180px; padding-top: 1.4rem; padding-bottom: 3rem;}
[data-testid="stMetricValue"] {font-size: 1.45rem;}
.hero {padding: 1.1rem 1.2rem; border: 1px solid #d9e2ef; border-radius: 14px; background: #f8fafc; margin-bottom: 1rem;}
.hero h1 {margin: 0; color: #17365D; font-size: 2rem;}
.hero p {margin: .35rem 0 0 0; color: #52606d;}
.small-card {padding:.8rem 1rem; border:1px solid #e4e8ee; border-radius:12px; background:#fff;}
.evidence {padding:.75rem .9rem; border-left:4px solid #4472C4; background:#f8fafc; border-radius:8px; margin:.4rem 0;}
div[data-testid="stTabs"] button {font-weight:600;}
</style>
""",unsafe_allow_html=True)

init_db()
if "case" not in st.session_state:
    st.session_state.case=fresh_case()
if "results" not in st.session_state:
    st.session_state.results=[]
if "last_query" not in st.session_state:
    st.session_state.last_query=""
if "followups" not in st.session_state:
    st.session_state.followups=[]

case=st.session_state.case

st.markdown("""
<div class="hero">
<h1>Gulf South Forgotten History</h1>
<p>A simple research workbench for people, businesses, places and overlooked regional stories.</p>
</div>
""",unsafe_allow_html=True)

tabs=st.tabs(["Search","Explore","Case","Timeline","Evidence","Reports","Advanced"])

with tabs[0]:
    st.subheader("What are you trying to find out?")
    q=st.text_area("Research question",value=case.get("question",""),
                   placeholder="Example: Who manufactured Tiger Cigars in New Orleans around 1890-1910?",
                   height=85,label_visibility="collapsed")
    rid=st.text_input(
        "Research subject / reference number",
        value=case.get("research_id",""),
        placeholder="Example: Tiger Cigars / CASE-2026-014",
        help="Use any name or case/reference number that will help you recognize this research later."
    )
    c1,c2,c3=st.columns([1.3,1,1])
    subject=c1.text_input("Who or what?",value=case.get("subject",""),placeholder="Person, business, building, brand...")
    location=c2.text_input("Place",value=case.get("location",""),placeholder="Covington, New Orleans...")
    depth=c3.radio("Depth",["Quick","Standard","Deep"],index=["Quick","Standard","Deep"].index(case.get("depth","Standard")),horizontal=True)
    y1,y2=st.columns(2)
    start=y1.number_input("From year",1700,2026,int(case.get("start_year",1874)))
    end=y2.number_input("To year",1700,2026,int(case.get("end_year",1922)))
    detected=infer_subject_type(subject+" "+q)
    st.caption(f"Research type detected: **{detected}**. The app chooses relevant sources and hides technical search options.")

    if st.button("START RESEARCH",type="primary",use_container_width=True):
        case.update({"research_id":rid,"subject":subject,"location":location,"start_year":int(start),"end_year":int(end),
                     "question":q,"depth":depth,"subject_type":detected})
        st.session_state.last_query=subject or q
        already=[x.get("signature") for x in case.get("search_log",[])]
        with st.spinner("Searching the most relevant free historical newspapers..."):
            results,log=progressive_search(subject or q,location,int(start),int(end),depth,q,already_searched=already)
        case["search_log"].extend(log)
        st.session_state.results=results
        if not results:
            case["negative_searches"].append({"query":subject or q,"location":location,"period":f"{start}-{end}"})
        st.rerun()

    if st.session_state.results:
        results=st.session_state.results
        st.subheader(f"Best matches ({len(results)})")
        st.caption("Near-duplicate results are grouped so repeated advertisements or notices do not bury the useful discoveries.")
        for i,r in enumerate(results):
            fresh = []
            try:
                from research_core import new_information
                fresh=new_information(r,case)
            except Exception:
                pass
            with st.container(border=True):
                top1,top2=st.columns([4,1])
                top1.markdown(f"**{r.get('newspaper','Newspaper')} - {r.get('date') or 'Undated'}**")
                top2.metric("Match",f"{r.get('score',0):.0f}")
                st.write(r.get("snippet",""))
                bits=[]
                if r.get("similar_count",1)>1: bits.append(f"{r['similar_count']} similar references grouped")
                if fresh: bits.append("New clues: "+", ".join(fresh[:4]))
                if bits: st.caption(" | ".join(bits))
                a,b,c=st.columns(3)
                if r.get("url"): a.link_button("View original",r["url"],use_container_width=True)
                if b.button("Save to case",key=f"save_{i}",use_container_width=True):
                    add_result_to_case(case,r); st.success("Saved.")
                if c.button("Follow clues",key=f"clue_{i}",use_container_width=True):
                    st.session_state.followups=best_followups(r,case,case.get("subject_type"))
                    st.rerun()

        if st.session_state.followups:
            st.markdown("### Best next clues")
            st.caption("Only high-value clues are shown. Weak or already-known branches are suppressed.")
            for x in st.session_state.followups:
                st.markdown(f"- **{x['lead']}** - {x['type']}: {x['why']}")
            chosen=st.selectbox("Use one clue as the next search",[""]+[x["lead"] for x in st.session_state.followups])
            if chosen and st.button("Search this clue",use_container_width=True):
                case["subject"]=chosen
                case["subject_type"]=infer_subject_type(chosen)
                st.session_state.last_query=chosen
                already=[x.get("signature") for x in case.get("search_log",[])]
                with st.spinner("Following the clue..."):
                    res,log=progressive_search(chosen,case.get("location",""),case.get("start_year",1874),case.get("end_year",1922),
                                              case.get("depth","Standard"),case.get("question",""),already_searched=already)
                case["search_log"].extend(log); st.session_state.results=res; st.rerun()

with tabs[1]:
    st.subheader("Explore a place")
    st.write("Use this when you do not already know the forgotten person, business or story you are looking for.")
    e1,e2=st.columns(2)
    place=e1.text_input("Town / neighborhood / parish",placeholder="Covington, Louisiana",key="explore_place")
    topic=e2.selectbox("What should we look for?",["Businesses","People","Buildings & Places","Organizations","Industry","Crime & Courts","Transportation","Everything"])
    a,b=st.columns(2)
    ey1=a.number_input("Explore from",1700,2026,1880,key="explore_y1")
    ey2=b.number_input("Explore to",1700,2026,1910,key="explore_y2")
    prompts={
        "Businesses":"business store company factory hotel bank mercantile",
        "People":"prominent citizen merchant physician attorney officer",
        "Buildings & Places":"building street hotel depot school church courthouse",
        "Organizations":"lodge association club society church council",
        "Industry":"factory mill railroad lumber cigar tobacco shipyard",
        "Crime & Courts":"court trial sheriff arrest murder burglary",
        "Transportation":"railroad depot steamer ferry road bridge",
        "Everything":"business citizen building lodge factory railroad court"
    }
    if st.button("DISCOVER FORGOTTEN HISTORY",type="primary",use_container_width=True):
        search_term=f"{place} {prompts[topic]}"
        with st.spinner("Looking for promising historical threads..."):
            res,log=progressive_search(search_term,place,int(ey1),int(ey2),"Deep",topic,already_searched=[])
        # Discovery mode intentionally returns the best bounded set rather than hundreds.
        st.session_state.explore_results=res[:30]
        case["search_log"].extend(log)
    for i,r in enumerate(st.session_state.get("explore_results",[])):
        with st.container(border=True):
            st.markdown(f"**{r.get('newspaper')} - {r.get('date') or 'Undated'}**")
            st.write(r.get("snippet",""))
            x,y=st.columns(2)
            if r.get("url"): x.link_button("View original",r["url"],use_container_width=True)
            if y.button("Start a case from this",key=f"discover_{i}",use_container_width=True):
                add_result_to_case(case,r)
                case["location"]=place; case["start_year"]=int(ey1); case["end_year"]=int(ey2)
                st.success("Added to your case.")

with tabs[2]:
    st.subheader("Research case")
    c1,c2=st.columns(2)
    case["case_name"]=c1.text_input("Project name",case.get("case_name",""),placeholder="Covington Cigar Makers")
    case["research_id"]=c2.text_input(
        "Research subject / reference number",
        case.get("research_id",""),
        placeholder="Example: Tiger Cigars / CASE-2026-014"
    )
    case["subject"]=st.text_input("Main subject",case.get("subject",""))
    case["notes"]=st.text_area("Notes",case.get("notes",""),height=90,placeholder="Your own notes, oral-history leads, questions...")
    m1,m2,m3=st.columns(3)
    m1.metric("Findings",len(case.get("results",[])))
    m2.metric("Entities",len(case.get("entities",[])))
    m3.metric("Searches logged",len(case.get("search_log",[])))

    if st.button("Find research gaps",use_container_width=True):
        case["generated_gaps"]=research_gaps(case)
    if case.get("generated_gaps"):
        st.markdown("### What may still be missing")
        for g in case["generated_gaps"]:
            st.markdown(f"- {g}")

    if case.get("subject_type")=="Business / Organization":
        with st.expander("Business research path"):
            for x in business_source_plan(case.get("subject",""),case.get("end_year",2026)):
                st.markdown(f"- {x}")

    st.markdown("### Recommended sources")
    for x in source_recommendations(case.get("subject_type","Person / Subject"),case.get("end_year",2026),case.get("question","")):
        st.markdown(f"- {x}")

    if case.get("results"):
        df=pd.DataFrame(case["results"])
        show=[c for c in ["date","newspaper","verification","snippet","url"] if c in df.columns]
        st.dataframe(df[show],use_container_width=True,hide_index=True)

    payload=json.dumps(case,indent=2).encode()
    backup_base=case.get("research_id") or case.get("case_name") or "history_case"
    st.download_button("Save case backup",payload,
                       file_name=re.sub(r"\W+","_",backup_base)+".json",
                       mime="application/json",use_container_width=True)
    up=st.file_uploader("Open a saved case",type=["json"])
    if up:
        try:
            st.session_state.case=json.load(up); st.success("Case opened."); st.rerun()
        except Exception:
            st.error("That does not look like a saved case file.")

with tabs[3]:
    st.subheader("Timeline")
    ev=case.get("events",[])
    if not ev:
        st.info("Save a few findings and the timeline will build itself.")
    else:
        df=pd.DataFrame(ev).drop_duplicates(subset=["date","source_id"]).sort_values("date")
        st.dataframe(df[[c for c in ["date","event","source","url"] if c in df.columns]],use_container_width=True,hide_index=True)
        years=[int(str(x)[:4]) for x in df["date"] if str(x)[:4].isdigit()]
        if len(years)>=2:
            st.caption(f"Known evidence currently spans {min(years)}-{max(years)}. Large gaps are good places to search next.")

with tabs[4]:
    st.subheader("Evidence")
    if not case.get("results"):
        st.info("Save a result to your case first.")
    else:
        labels=[]
        for i,r in enumerate(case["results"]):
            labels.append(f"{i+1}. {r.get('date') or 'Undated'} - {r.get('newspaper') or r.get('title')}")
        idx=st.selectbox("Choose a finding",range(len(labels)),format_func=lambda i:labels[i])
        r=case["results"][idx]
        st.markdown('<div class="evidence"><b>Finding</b><br>'+str(r.get("snippet",""))+'</div>',unsafe_allow_html=True)
        st.link_button("SHOW ME THE ORIGINAL",r.get("url",""),use_container_width=True)
        status_options=["Needs review","Verified","Corroborated","Probable","Possible","Lead"]
        current=r.get("verification","Needs review")
        if current not in status_options: current="Needs review"
        r["verification"]=st.selectbox("Evidence status",status_options,index=status_options.index(current))
        st.caption("Verified = checked against the original/authoritative source. Corroborated = supported by multiple independent sources.")

        if st.button("Show extracted clues",use_container_width=True):
            page=get_page(r.get("id",""))
            ents=extract_entities((page or {}).get("full_text") or r.get("snippet",""))
            st.json(ents)

        with st.expander("OCR verification - only when needed"):
            page=get_page(r.get("id",""))
            if page:
                st.text_area("Original OCR",page.get("full_text",""),height=220,disabled=True)
                corrected=st.text_area("Cleaned / corrected OCR",page.get("corrected_text",""),height=180)
                verified=st.text_area("Human-verified transcription",page.get("verified_text",""),height=180)
                if st.button("Save OCR corrections"):
                    update_text(page["id"],corrected=corrected,verified=verified); st.success("Saved without overwriting the original OCR.")

    if case.get("entities"):
        with st.expander("People, businesses, organizations and addresses"):
            edf=pd.DataFrame(case["entities"])
            st.dataframe(edf,use_container_width=True,hide_index=True)

with tabs[5]:
    st.subheader("Reports")
    st.write("Use PDF when you want a polished report. Use Excel when you want to sort, filter and continue working.")
    case["generated_gaps"]=case.get("generated_gaps") or research_gaps(case)
    p1,p2=st.columns(2)
    with p1:
        st.markdown("### Professional PDF")
        if case.get("results"):
            pdf=make_pdf(case,SOURCE_REGISTRY)
            report_base=case.get("research_id") or case.get("case_name") or case.get("subject") or "research"
            name=re.sub(r"\W+","_",report_base).strip("_")+"_Research_Report.pdf"
            st.download_button("Create / Download PDF",pdf,file_name=name,mime="application/pdf",type="primary",use_container_width=True)
            st.caption("On iPad: open the PDF, tap Share, then choose Mail, Files, AirDrop or Print.")
        else:
            st.info("Save at least one finding first.")
    with p2:
        st.markdown("### Research Excel workbook")
        if case.get("results") or case.get("entities"):
            xlsx=make_excel(case,SOURCE_REGISTRY)
            report_base=case.get("research_id") or case.get("case_name") or case.get("subject") or "research"
            name=re.sub(r"\W+","_",report_base).strip("_")+"_Research_Workbook.xlsx"
            st.download_button("Create / Download Excel",xlsx,file_name=name,
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               type="primary",use_container_width=True)
            st.caption("Overview is always first. Extra tabs appear only when the case results justify them.")
        else:
            st.info("Save some research first.")

with tabs[6]:
    st.subheader("Advanced")
    st.caption("Most researchers never need these controls.")
    with st.expander("Free source map"):
        st.dataframe(pd.DataFrame(SOURCE_REGISTRY),use_container_width=True,hide_index=True)
    with st.expander("Regional newspapers searched automatically"):
        rows=[{"Newspaper":k,**v} for k,v in NEWSPAPERS.items()]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    with st.expander("Search log / negative research"):
        if case.get("search_log"):
            st.dataframe(pd.DataFrame(case["search_log"]),use_container_width=True,hide_index=True)
        if case.get("negative_searches"):
            st.markdown("**Searches with no useful result:**")
            st.dataframe(pd.DataFrame(case["negative_searches"]),use_container_width=True,hide_index=True)
    with st.expander("Research rules"):
        st.markdown("""
- Search the strongest clues first.
- Use new names, addresses, organizations and exact identifiers to narrow later searches.
- Do not keep repeating weak branches.
- A newspaper report is not the same thing as an official record.
- Co-occurrence is not proof of a relationship.
- No online match does not mean no record exists.
- Verify important facts against the original document.
        """)

st.divider()
st.caption("Free by design: the core app uses free hosting-compatible Python libraries and free public sources. Restricted archives are identified, not bypassed.")
