
from __future__ import annotations
from io import BytesIO
import datetime as dt, re
import xlsxwriter
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether
)

def esc(x):
    return (str(x or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))

def _section(story,title,styles):
    story.append(Spacer(1,8))
    story.append(Paragraph(esc(title),styles["Section"]))
    story.append(Spacer(1,4))

def make_pdf(case, source_registry):
    buf=BytesIO()
    doc=SimpleDocTemplate(
        buf,pagesize=letter,rightMargin=48,leftMargin=48,topMargin=52,bottomMargin=48,
        title=case.get("case_name") or case.get("subject") or "Research Report",
        author="Gulf South Forgotten History Research"
    )
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverTitle",parent=styles["Title"],fontName="Helvetica-Bold",
                              fontSize=22,leading=27,textColor=colors.HexColor("#17365D"),
                              alignment=TA_CENTER,spaceAfter=14))
    styles.add(ParagraphStyle(name="CoverSub",parent=styles["Normal"],fontSize=11,leading=16,
                              textColor=colors.HexColor("#555555"),alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="Section",parent=styles["Heading2"],fontName="Helvetica-Bold",
                              fontSize=13,leading=16,textColor=colors.HexColor("#17365D"),
                              spaceBefore=8,spaceAfter=5))
    styles.add(ParagraphStyle(name="Small",parent=styles["Normal"],fontSize=8.5,leading=11,
                              textColor=colors.HexColor("#555555")))
    styles.add(ParagraphStyle(name="Finding",parent=styles["Normal"],fontSize=9.5,leading=13,
                              spaceAfter=5))
    styles.add(ParagraphStyle(name="Label",parent=styles["Normal"],fontName="Helvetica-Bold",
                              fontSize=8.5,leading=11,textColor=colors.HexColor("#17365D")))

    story=[]
    subject=case.get("subject") or case.get("case_name") or "Research Subject"
    story += [
        Spacer(1,72),
        Paragraph("GULF SOUTH FORGOTTEN HISTORY",styles["CoverTitle"]),
        Paragraph("Source-Documented Research Report",styles["CoverSub"]),
        Spacer(1,28),
        Paragraph(esc(subject),styles["CoverTitle"]),
        Spacer(1,12),
        Paragraph(f"Reference: {esc(case.get('research_id') or 'Not assigned')}",styles["CoverSub"]),
        Paragraph(f"Location: {esc(case.get('location') or 'Not specified')}",styles["CoverSub"]),
        Paragraph(f"Period: {esc(case.get('start_year'))} - {esc(case.get('end_year'))}",styles["CoverSub"]),
        Paragraph(f"Research depth: {esc(case.get('depth') or 'Standard')}",styles["CoverSub"]),
        Paragraph(f"Generated: {dt.datetime.now().strftime('%B %d, %Y')}",styles["CoverSub"]),
        Spacer(1,52),
        Paragraph("Evidence-first research: OCR and automated analysis locate candidates; original records support findings.",styles["Small"]),
        PageBreak()
    ]

    _section(story,"1. Executive Summary",styles)
    results=case.get("results",[])
    verified=[r for r in results if (r.get("verification") or "").lower() in ("verified","corroborated")]
    summary = (
        f"This report contains {len(results)} saved finding(s), {len(case.get('entities',[]))} discovered entity/entities, "
        f"and {len(case.get('events',[]))} timeline event(s). "
        f"{len(verified)} finding(s) are currently marked verified or corroborated."
    )
    story.append(Paragraph(esc(summary),styles["Finding"]))
    if case.get("question"):
        story.append(Paragraph("<b>Research question:</b> "+esc(case["question"]),styles["Finding"]))

    _section(story,"2. Research Scope",styles)
    scope=[
        ["Research Reference",case.get("research_id","")],
        ["Subject",case.get("subject","")],
        ["Subject Type",case.get("subject_type","")],
        ["Geographic Focus",case.get("location","")],
        ["Date Range",f"{case.get('start_year','')} - {case.get('end_year','')}"],
        ["Depth",case.get("depth","")],
    ]
    t=Table(scope,colWidths=[120,360])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,-1),colors.HexColor("#EAF0F7")),
        ("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),
        ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#D9E2F3")),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("FONTSIZE",(0,0),(-1,-1),9),
        ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
    ]))
    story.append(t)

    if results:
        _section(story,"3. Key Findings",styles)
        for i,r in enumerate(results[:25],1):
            status=r.get("verification") or "Needs review"
            title=f"{i}. {r.get('date') or 'Undated'} - {r.get('newspaper') or r.get('title') or 'Source'}"
            block=[
                Paragraph(esc(title),styles["Label"]),
                Paragraph(esc(r.get("snippet","")),styles["Finding"]),
                Paragraph(f"<b>Status:</b> {esc(status)} &nbsp;&nbsp; <b>Source:</b> {esc(r.get('url',''))}",styles["Small"]),
                Spacer(1,6)
            ]
            story.append(KeepTogether(block))

    events=case.get("events",[])
    if events:
        _section(story,"4. Chronological Timeline",styles)
        rows=[["Date","Event","Source"]]
        for e in sorted(events,key=lambda x:str(x.get("date","")))[:100]:
            rows.append([e.get("date",""),e.get("event","")[:220],e.get("source","")])
        t=Table(rows,colWidths=[70,325,85],repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#D9E2F3")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),("FONTSIZE",(0,0),(-1,-1),7.5),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F8FAFC")]),
        ]))
        story.append(t)

    entities=case.get("entities",[])
    if entities:
        _section(story,"5. People, Businesses, Organizations & Places",styles)
        rows=[["Type","Name","Context","Confidence"]]
        for e in entities[:120]:
            rows.append([e.get("type",""),e.get("name",""),e.get("context",""),e.get("confidence","")])
        t=Table(rows,colWidths=[85,125,210,60],repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#D9E2F3")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),("FONTSIZE",(0,0),(-1,-1),7.5),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F8FAFC")]),
        ]))
        story.append(t)

    # Dynamic topical sections.
    joined=" ".join((r.get("snippet","")+" "+r.get("title","")) for r in results).lower()
    topical=[
        ("6. Newspaper & Advertisement Findings",["newspaper","farmer","echo","times","democrat","advertis","mercantile"]),
        ("7. Business & Organization Findings",["company","business","store","factory","corporation","lodge","association","contractor"]),
        ("8. Genealogy & People Findings",["census","obituary","death","marriage","birth","cemetery","voter"]),
        ("9. Government, Contract & Political Findings",["contract","budget","audit","council","ordinance","campaign","election","procurement"]),
        ("10. Historical Archive Findings",["archive","collection","library","manuscript","photograph","map"]),
    ]
    n=6
    for title,keywords in topical:
        matching=[r for r in results if any(k in ((r.get("snippet","")+" "+r.get("title","")).lower()) for k in keywords)]
        if matching:
            _section(story,title,styles)
            for r in matching[:20]:
                story.append(Paragraph(
                    f"<b>{esc(r.get('date') or 'Undated')} - {esc(r.get('newspaper') or r.get('title'))}</b><br/>{esc(r.get('snippet',''))}",
                    styles["Finding"]
                ))

    gaps=case.get("generated_gaps") or []
    if gaps:
        _section(story,"Research Gaps & Next Steps",styles)
        for g in gaps:
            story.append(Paragraph("- "+esc(g),styles["Finding"]))

    if case.get("notes"):
        _section(story,"Research Notes",styles)
        story.append(Paragraph(esc(case["notes"]).replace("\n","<br/>"),styles["Finding"]))

    _section(story,"Research Methodology",styles)
    story.append(Paragraph(
        "The research process begins with the strongest known identifiers, searches the most relevant sources first, "
        "extracts newly discovered names, organizations, addresses, dates and identifiers, and then uses those discoveries "
        "to make narrower follow-up searches. Duplicate results are suppressed, weak branches are not repeated, and important "
        "facts should be checked against the original source before being treated as established.",
        styles["Finding"]
    ))

    _section(story,"Source Search Log",styles)
    log=case.get("search_log",[])
    if log:
        rows=[["Source","Query","Status"]]
        for x in log[:150]:
            rows.append([x.get("source",""),x.get("query",""),x.get("status","")])
        t=Table(rows,colWidths=[120,260,100],repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#D9E2F3")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),("FONTSIZE",(0,0),(-1,-1),7.5),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No automated search log has been saved.",styles["Finding"]))

    _section(story,"Available Research Sources",styles)
    rows=[["Family","Source","Access"]]
    for x in source_registry:
        rows.append([x.get("family",""),x.get("source",""),x.get("access","")])
    t=Table(rows,colWidths=[80,280,120],repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#D9E2F3")),
        ("VALIGN",(0,0),(-1,-1),"TOP"),("FONTSIZE",(0,0),(-1,-1),7.5),
    ]))
    story.append(t)

    _section(story,"Limitations",styles)
    story.append(Paragraph(
        "A source marked Open & search was not necessarily searched automatically. 'No online match' does not mean that no record exists. "
        "Some historical records remain undigitized, unindexed, restricted, or available only through a library, archive, courthouse, or records custodian. "
        "AI/OCR observations are research aids, not independent evidence.",
        styles["Finding"]
    ))
    doc.build(story)
    return buf.getvalue()

def make_excel(case, source_registry):
    output=BytesIO()
    wb=xlsxwriter.Workbook(output,{"in_memory":True})
    wb.set_properties({
        "title":case.get("case_name") or case.get("subject") or "Research Workbook",
        "subject":"Gulf South Forgotten History source-documented research workbook",
        "author":"Gulf South Forgotten History Research"
    })
    title=wb.add_format({"bold":True,"font_size":20,"font_color":"#17365D"})
    sub=wb.add_format({"font_size":10,"font_color":"#666666","italic":True})
    section=wb.add_format({"bold":True,"font_size":12,"font_color":"#FFFFFF","bg_color":"#17365D"})
    header=wb.add_format({"bold":True,"font_color":"#FFFFFF","bg_color":"#4472C4","border":1,"text_wrap":True,"valign":"vcenter"})
    body=wb.add_format({"border":1,"border_color":"#E7E6E6","valign":"top","text_wrap":True})
    link=wb.add_format({"font_color":"#0563C1","underline":True,"border":1,"border_color":"#E7E6E6","valign":"top"})
    note=wb.add_format({"font_color":"#666666","italic":True,"text_wrap":True})

    results=case.get("results",[]); entities=case.get("entities",[]); events=case.get("events",[])

    ws=wb.add_worksheet("Overview"); ws.hide_gridlines(2)
    ws.set_column("A:A",22); ws.set_column("B:B",58); ws.set_column("C:D",20)
    ws.write("A1","Gulf South Forgotten History",title); ws.write("A2","Research workbook",sub)
    ws.write("A4","Case Overview",section)
    overview=[
        ["Case Name",case.get("case_name","")],["Research Reference",case.get("research_id","")],["Subject",case.get("subject","")],
        ["Subject Type",case.get("subject_type","")],["Location",case.get("location","")],
        ["Period",f"{case.get('start_year','')} - {case.get('end_year','')}"],
        ["Research Question",case.get("question","")],["Depth",case.get("depth","")],
        ["Saved Findings",len(results)],["Entities",len(entities)],["Timeline Events",len(events)]
    ]
    for i,(a,b) in enumerate(overview,start=5):
        ws.write(i-1,0,a,header); ws.write(i-1,1,b,body)
    ws.write("A17","Evidence Rule",section)
    ws.merge_range("A18:D20","OCR and automated analysis locate candidates. Verify important facts against original records. Co-occurrence does not prove a relationship.",note)

    def add_findings_sheet(name, rows):
        if not rows: return
        ws=wb.add_worksheet(name[:31]); ws.hide_gridlines(2)
        headers=["Date","Source","Finding / OCR Snippet","Verification","Score","Original Source"]
        ws.write_row(0,0,headers,header)
        for c,w in enumerate([14,30,70,16,10,42]): ws.set_column(c,c,w)
        for i,r in enumerate(rows,start=1):
            ws.write(i,0,r.get("date",""),body)
            ws.write(i,1,r.get("newspaper") or r.get("title",""),body)
            ws.write(i,2,r.get("snippet",""),body)
            ws.write(i,3,r.get("verification","Needs review"),body)
            ws.write(i,4,r.get("score",""),body)
            url=r.get("url","")
            if str(url).startswith(("http://","https://")): ws.write_url(i,5,url,link,string="View Original")
            else: ws.write(i,5,url,body)
        ws.autofilter(0,0,len(rows),len(headers)-1); ws.freeze_panes(1,0)

    add_findings_sheet("Findings",results)

    if events:
        ws=wb.add_worksheet("Timeline"); ws.hide_gridlines(2)
        ws.write_row(0,0,["Date","Event","Source","URL"],header)
        for c,w in enumerate([14,70,28,42]): ws.set_column(c,c,w)
        for i,e in enumerate(sorted(events,key=lambda x:str(x.get("date",""))),1):
            ws.write(i,0,e.get("date",""),body); ws.write(i,1,e.get("event",""),body)
            ws.write(i,2,e.get("source",""),body)
            url=e.get("url","")
            if str(url).startswith(("http://","https://")): ws.write_url(i,3,url,link,string="View Source")
            else: ws.write(i,3,url,body)
        ws.autofilter(0,0,len(events),3); ws.freeze_panes(1,0)

    if entities:
        ws=wb.add_worksheet("People & Organizations"); ws.hide_gridlines(2)
        ws.write_row(0,0,["Type","Name","Context","Source","Confidence"],header)
        for c,w in enumerate([22,34,52,42,16]): ws.set_column(c,c,w)
        for i,e in enumerate(entities,1):
            ws.write_row(i,0,[e.get("type",""),e.get("name",""),e.get("context",""),e.get("source",""),e.get("confidence","")],body)
        ws.autofilter(0,0,len(entities),4); ws.freeze_panes(1,0)

    # Dynamic tabs based on result content.
    topical=[
        ("Newspapers",["farmer","echo","times","democrat","newspaper","advertis"]),
        ("Business & Organizations",["company","business","store","factory","corporation","lodge","association"]),
        ("Genealogy",["census","obituary","death","birth","marriage","cemetery","voter","family"]),
        ("Government",["government","parish","council","ordinance","resolution","budget","audit"]),
        ("Contracts & Spending",["contract","procurement","vendor","bid","rfp","award","purchase","expenditure"]),
        ("Political Records",["campaign","election","candidate","ethics","lobby","legislative","contribution"]),
        ("Historical Archives",["archive","collection","library","manuscript","photograph","map"]),
    ]
    for name,keys in topical:
        matching=[r for r in results if any(k in ((r.get("snippet","")+" "+r.get("title","")).lower()) for k in keys)]
        add_findings_sheet(name,matching)

    ws=wb.add_worksheet("Sources"); ws.hide_gridlines(2)
    ws.write_row(0,0,["Family","Source","Area","Access","Cost","Best Used For"],header)
    for c,w in enumerate([16,36,28,20,20,58]): ws.set_column(c,c,w)
    for i,x in enumerate(source_registry,1):
        ws.write_row(i,0,[x.get("family",""),x.get("source",""),x.get("area",""),x.get("access",""),x.get("cost",""),x.get("purpose","")],body)
    ws.autofilter(0,0,len(source_registry),5); ws.freeze_panes(1,0)

    log=case.get("search_log",[])
    if log:
        ws=wb.add_worksheet("Search Log"); ws.hide_gridlines(2)
        ws.write_row(0,0,["Source","Query","Status","Signature"],header)
        for c,w in enumerate([28,55,24,45]): ws.set_column(c,c,w)
        for i,x in enumerate(log,1):
            ws.write_row(i,0,[x.get("source",""),x.get("query",""),x.get("status",""),x.get("signature","")],body)
        ws.autofilter(0,0,len(log),3); ws.freeze_panes(1,0)

    ws=wb.add_worksheet("Research Notes"); ws.hide_gridlines(2)
    ws.set_column("A:A",25); ws.set_column("B:B",80)
    ws.write("A1","Research Notes & Gaps",title)
    ws.write_row("A3",["Item","Notes"],header)
    ws.write("A4","Case Notes",body); ws.write("B4",case.get("notes",""),body)
    ws.write("A5","Research Gaps",body); ws.write("B5","\n".join(case.get("generated_gaps",[])),body)
    ws.write("A6","Unanswered Questions",body); ws.write("B6","\n".join(case.get("questions",[])),body)
    ws.write("A7","Limitation",body); ws.write("B7","No online match does not mean no record exists. Some sources may be undigitized, unindexed, restricted, or require an archive/library visit.",body)

    wb.close(); output.seek(0)
    return output.getvalue()
