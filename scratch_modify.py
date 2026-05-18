import re
from pathlib import Path

def update_file():
    path = Path("presentation/build_pptx.py")
    content = path.read_text(encoding="utf-8")

    # slide_02_agenda
    orig_slide_02 = """def slide_02_agenda():
    s = prs.slides.add_slide(BLANK); add_bg(s)
    add_chrome(s, "Plan de la présentation", "Hamza", 2)

    parts = [
        ("01", "Introduction & Architecture", "Hamza Bjibji",
         "Contexte, objectifs, architecture\\nglobale et démo de la plateforme",
         ACCENT_BLUE),
        ("02", "GitHub Monitoring", "Chaimae Ben Sbeh",
         "Détection de secrets exposés\\ndans les dépôts publics GitHub",
         ACCENT_TEAL),
        ("03", "Telegram & Google Alerts", "Yassir Salim El Akramine",
         "Veille communautaire OSINT\\net couverture médiatique",
         ACCENT_AMBER),
        ("04", "BI Threat Intel & Conclusion", "Imane Sghiouar",
         "Module CVE Bronze/Silver/Gold,\\nclassification & perspectives",
         ACCENT_VIOLET),
    ]

    card_w = Inches(2.95); card_h = Inches(4.5)
    gap    = Inches(0.15)
    total_w = card_w * 4 + gap * 3
    x0 = (SW - total_w) / 2
    y0 = Inches(1.7)

    for i, (num, title, name, desc, color) in enumerate(parts):
        x = x0 + i * (card_w + gap)
        # Card
        add_rect(s, x, y0, card_w, card_h, fill=CARD_BG, line=BORDER_LINE, corner=True)
        # Color stripe
        add_rect(s, x, y0, card_w, Inches(0.18), fill=color, corner=False)
        # Big number
        add_text(s, x + Inches(0.3), y0 + Inches(0.5), card_w - Inches(0.6), Inches(1.5),
                 num, size=72, bold=True, color=color)
        # Title
        add_text(s, x + Inches(0.3), y0 + Inches(2.0), card_w - Inches(0.6), Inches(1.0),
                 title, size=16, bold=True, color=TEXT_PRIMARY)
        # Divider
        add_line(s, x + Inches(0.3), y0 + Inches(2.95),
                 x + Inches(1.3), y0 + Inches(2.95), color=color, weight=2)
        # Description
        add_text(s, x + Inches(0.3), y0 + Inches(3.05), card_w - Inches(0.6), Inches(0.9),
                 desc, size=10, color=TEXT_SEC)
        # Presenter name
        add_text(s, x + Inches(0.3), y0 + Inches(4.0), card_w - Inches(0.6), Inches(0.35),
                 name, size=10, bold=True, color=color)"""
                 
    new_slide_02 = """def slide_02_agenda():
    s = prs.slides.add_slide(BLANK); add_bg(s)
    add_chrome(s, "Plan de la présentation", "Hamza", 2)

    parts = [
        ("01", "Introduction & Architecture", "Hamza Bjibji",
         "Contexte, objectifs, architecture\\nglobale et démo de la plateforme",
         ACCENT_BLUE),
        ("02", "GitHub Monitoring", "Chaimae Ben Sbeh",
         "Détection de secrets exposés\\ndans les dépôts publics GitHub",
         ACCENT_TEAL),
        ("03", "Telegram & Google Alerts", "Yassir Salim El Akramine",
         "Veille communautaire OSINT\\net couverture médiatique",
         ACCENT_AMBER),
        ("04", "BI Threat Intel & Conclusion", "Imane Sghiouar",
         "Module CVE Bronze/Silver/Gold,\\nclassification & perspectives",
         ACCENT_VIOLET),
    ]

    # Elegant horizontal timeline
    timeline_y = Inches(4.0)
    add_line(s, Inches(1.0), timeline_y, SW - Inches(1.0), timeline_y, color=BORDER_LINE, weight=4)

    step_w = (SW - Inches(2.0)) / 4
    x0 = Inches(1.0)

    for i, (num, title, name, desc, color) in enumerate(parts):
        cx = x0 + i * step_w + step_w / 2
        
        # Connection to timeline
        if i % 2 == 0:
            add_line(s, cx, timeline_y, cx, timeline_y - Inches(1.5), color=color, weight=2)
            card_y = timeline_y - Inches(2.5)
            # Dot on timeline
            dot = s.shapes.add_shape(MSO_SHAPE.OVAL, cx - Inches(0.1), timeline_y - Inches(0.1), Inches(0.2), Inches(0.2))
            dot.line.fill.background(); dot.fill.solid(); dot.fill.fore_color.rgb = color
            # Number above
            add_text(s, cx - Inches(0.5), timeline_y - Inches(0.4), Inches(1.0), Inches(0.3), num, size=14, bold=True, color=color, align="center")
        else:
            add_line(s, cx, timeline_y, cx, timeline_y + Inches(1.5), color=color, weight=2)
            card_y = timeline_y + Inches(0.5)
            # Dot on timeline
            dot = s.shapes.add_shape(MSO_SHAPE.OVAL, cx - Inches(0.1), timeline_y - Inches(0.1), Inches(0.2), Inches(0.2))
            dot.line.fill.background(); dot.fill.solid(); dot.fill.fore_color.rgb = color
            # Number below
            add_text(s, cx - Inches(0.5), timeline_y + Inches(0.1), Inches(1.0), Inches(0.3), num, size=14, bold=True, color=color, align="center")

        # Info Box
        cw = Inches(2.6)
        bx = cx - cw/2
        add_text(s, bx, card_y, cw, Inches(0.4), title, size=14, bold=True, color=TEXT_PRIMARY, align="center")
        add_text(s, bx, card_y + Inches(0.4), cw, Inches(0.6), desc, size=10, color=TEXT_SEC, align="center")
        add_badge(s, cx - Inches(0.75), card_y + Inches(0.9), Inches(1.5), Inches(0.25), name, fill=CARD_BG_2, color=color, size=8)"""

    content = content.replace(orig_slide_02, new_slide_02)
    
    path.write_text(content, encoding="utf-8")
    print("Done")

if __name__ == "__main__":
    update_file()
