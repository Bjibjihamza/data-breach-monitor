import re
from pathlib import Path

def update_slides():
    p = Path("presentation/build_pptx.py")
    content = p.read_text(encoding="utf-8")

    # Slide 5
    orig_slide_5 = """def slide_05_architecture():
    s = prs.slides.add_slide(BLANK); add_bg(s)
    add_chrome(s, "Architecture & sources intégrées", "Hamza", 5)

    # LEFT — Diagram
    add_text(s, Inches(0.7), Inches(1.55), Inches(7), Inches(0.4),
             "PIPELINE GLOBAL", size=10, bold=True, color=ACCENT_BLUE)
    img_path = IMG / "diagramme_concep.png"
    if img_path.exists():
        add_image(s, img_path, Inches(0.7), Inches(2.0), w=Inches(7.5))
    else:
        add_rect(s, Inches(0.7), Inches(2.0), Inches(7.5), Inches(4.5),
                 fill=CARD_BG, line=BORDER_LINE, corner=True)
        add_text(s, Inches(0.7), Inches(4.0), Inches(7.5), Inches(0.5),
                 "[Diagramme du pipeline]", size=14, color=TEXT_SEC,
                 align="center", anchor="middle")

    # RIGHT — sources mini-table
    right_x = Inches(8.5); right_w = Inches(4.3)
    add_text(s, right_x, Inches(1.55), right_w, Inches(0.4),
             "4 SOURCES COMPLÉMENTAIRES", size=10, bold=True, color=ACCENT_BLUE)

    sources = [
        ("GitHub",        "Preuves techniques\\nd'exposition",        ACCENT_BLUE),
        ("Telegram",      "Signaux communautaires\\nprécoces",        ACCENT_TEAL),
        ("Google Alerts", "Veille médiatique\\nOSINT",                ACCENT_AMBER),
        ("CVE / BI",      "Vision quantitative\\ndes vulnérabilités", ACCENT_VIOLET),
    ]
    sy = Inches(2.0)
    for name, desc, color in sources:
        add_rect(s, right_x, sy, right_w, Inches(1.0), fill=CARD_BG, line=BORDER_LINE, corner=True)
        add_rect(s, right_x, sy, Inches(0.08), Inches(1.0), fill=color)
        add_text(s, right_x + Inches(0.25), sy + Inches(0.1), right_w - Inches(0.5),
                 Inches(0.4), name, size=14, bold=True, color=color)
        add_text(s, right_x + Inches(0.25), sy + Inches(0.45), right_w - Inches(0.5),
                 Inches(0.6), desc, size=10, color=TEXT_SEC)
        sy += Inches(1.13)

    # Bottom — 4 principles bar
    add_rect(s, Inches(0.7), Inches(6.6), Inches(12.1), Inches(0.5),
             fill=CARD_BG_2, corner=True)
    principles = [
        ("Séparation des responsabilités", ACCENT_BLUE),
        ("Config externalisée",            ACCENT_TEAL),
        ("Filtrage explicite",             ACCENT_AMBER),
        ("Approche défensive",             ACCENT_GREEN),
    ]
    pw = Inches(12.1) / 4
    for i, (txt, c) in enumerate(principles):
        px = Inches(0.7) + i * pw
        # bullet dot
        dot = s.shapes.add_shape(MSO_SHAPE.OVAL, px + Inches(0.2), Inches(6.78),
                                 Inches(0.14), Inches(0.14))
        dot.line.fill.background(); dot.fill.solid(); dot.fill.fore_color.rgb = c
        dot.shadow.inherit = False
        add_text(s, px + Inches(0.45), Inches(6.65), pw - Inches(0.5), Inches(0.4),
                 txt, size=10, bold=True, color=TEXT_PRIMARY, anchor="middle")"""

    new_slide_5 = """def slide_05_architecture():
    s = prs.slides.add_slide(BLANK); add_bg(s)
    add_chrome(s, "Architecture & sources intégrées", "Hamza", 5)

    # LEFT — Diagram (Bigger)
    add_text(s, Inches(0.7), Inches(1.55), Inches(7), Inches(0.4),
             "PIPELINE GLOBAL", size=10, bold=True, color=ACCENT_BLUE)
    img_path = IMG / "diagramme_concep.png"
    if img_path.exists():
        add_rect(s, Inches(0.7), Inches(1.95), Inches(8.0), Inches(4.5), fill=CARD_BG, line=BORDER_FAINT, corner=True)
        add_image(s, img_path, Inches(0.8), Inches(2.05), w=Inches(7.8))
    else:
        add_rect(s, Inches(0.7), Inches(2.0), Inches(8.0), Inches(4.5),
                 fill=CARD_BG, line=BORDER_FAINT, corner=True)
        add_text(s, Inches(0.7), Inches(4.0), Inches(8.0), Inches(0.5),
                 "[Diagramme du pipeline]", size=14, color=TEXT_SEC,
                 align="center", anchor="middle")

    # RIGHT — sources mini-table (Clean Side Panel)
    right_x = Inches(9.0); right_w = Inches(3.8)
    add_text(s, right_x, Inches(1.55), right_w, Inches(0.4),
             "SOURCES", size=10, bold=True, color=ACCENT_BLUE)

    sources = [
        ("GitHub",        "Preuves techniques",        ACCENT_BLUE),
        ("Telegram",      "Signaux OSINT",        ACCENT_TEAL),
        ("Google Alerts", "Veille médiatique",                ACCENT_AMBER),
        ("CVE / BI",      "Vulnérabilités", ACCENT_VIOLET),
    ]
    sy = Inches(1.95)
    for name, desc, color in sources:
        # Subtle glass-like card without borders
        add_rect(s, right_x, sy, right_w, Inches(0.85), fill=CARD_BG_2, corner=True)
        add_rect(s, right_x, sy, Inches(0.06), Inches(0.85), fill=color)
        add_text(s, right_x + Inches(0.25), sy + Inches(0.15), right_w - Inches(0.5),
                 Inches(0.3), name, size=13, bold=True, color=color)
        add_text(s, right_x + Inches(0.25), sy + Inches(0.45), right_w - Inches(0.5),
                 Inches(0.3), desc, size=10, color=TEXT_SEC)
        sy += Inches(0.95)

    # Bottom — principles as elegant tags
    add_text(s, right_x, Inches(5.8), right_w, Inches(0.3), "PRINCIPES", size=9, bold=True, color=TEXT_MUTED)
    principles = [
        "Séparation des responsabilités",
        "Config externalisée",
        "Approche défensive",
    ]
    py = Inches(6.1)
    for txt in principles:
        add_badge(s, right_x, py, right_w, Inches(0.28), txt, fill=CARD_BG_2, color=TEXT_PRIMARY, size=8, bold=False)
        py += Inches(0.35)"""
    content = content.replace(orig_slide_5, new_slide_5)

    # Slide 6
    content = content.replace('''    if (IMG / "overview.png").exists():
        # Card around image
        add_rect(s, Inches(0.4), Inches(1.95), Inches(7.95), Inches(4.6),
                 fill=CARD_BG, line=BORDER_LINE, corner=True)
        add_image(s, IMG / "overview.png",
                  Inches(0.55), Inches(2.1), w=Inches(7.65))''',
'''    if (IMG / "overview.png").exists():
        add_browser_frame(s, Inches(0.4), Inches(1.95), Inches(7.95), Inches(4.6),
                          img_path=IMG / "overview.png", title="dbm.soc.local/overview")''')

    # Slide 8
    content = content.replace('''    if (IMG / "github_1.png").exists():
        add_rect(s, Inches(7.7), Inches(3.9), Inches(5.25), Inches(3.0),
                 fill=CARD_BG, line=BORDER_LINE, corner=True)
        add_image(s, IMG / "github_1.png",
                  Inches(7.85), Inches(4.05), w=Inches(4.95))''',
'''    if (IMG / "github_1.png").exists():
        add_browser_frame(s, Inches(7.7), Inches(3.9), Inches(5.25), Inches(3.0),
                          img_path=IMG / "github_1.png", title="dbm.soc.local/github/scans")''')

    # Slide 9
    content = content.replace('''    if (IMG / "githubexposure.png").exists():
        add_rect(s, Inches(0.4), Inches(2.4), Inches(7.6), Inches(4.5),
                 fill=CARD_BG, line=BORDER_LINE, corner=True)
        add_image(s, IMG / "githubexposure.png",
                  Inches(0.55), Inches(2.55), w=Inches(7.3))''',
'''    if (IMG / "githubexposure.png").exists():
        add_browser_frame(s, Inches(0.4), Inches(2.4), Inches(7.6), Inches(4.5),
                          img_path=IMG / "githubexposure.png", title="github.com/exposure/config.js")''')

    # Slide 10
    content = content.replace('''    if (IMG / "tg_dash.png").exists():
        add_rect(s, Inches(0.4), Inches(3.05), Inches(7.7), Inches(3.85),
                 fill=CARD_BG, line=BORDER_LINE, corner=True)
        add_image(s, IMG / "tg_dash.png",
                  Inches(0.55), Inches(3.2), w=Inches(7.4))''',
'''    if (IMG / "tg_dash.png").exists():
        add_browser_frame(s, Inches(0.4), Inches(3.05), Inches(7.7), Inches(3.85),
                          img_path=IMG / "tg_dash.png", title="dbm.soc.local/telegram/overview")''')

    # Slide 11
    content = content.replace('''    # Card holding screenshot + meta
    add_rect(s, rx, Inches(1.95), rw, Inches(4.95),
             fill=CARD_BG, line=ACCENT_RED, line_w=1.2, corner=True)

    # Embedded screenshot
    if (IMG / "tg_exposure.png").exists():
        add_image(s, IMG / "tg_exposure.png",
                  rx + Inches(0.2), Inches(2.1), w=rw - Inches(0.4))''',
'''    # Card holding screenshot + meta
    add_browser_frame(s, rx, Inches(1.95), rw, Inches(4.95), img_path=IMG / "tg_exposure.png", title="t.me/breachforums_cdn")''')

    # Slide 12
    content = content.replace('''    if (IMG / "gaw.png").exists():
        add_rect(s, Inches(0.4), Inches(2.95), Inches(5.95), Inches(3.95),
                 fill=CARD_BG, line=BORDER_LINE, corner=True)
        add_image(s, IMG / "gaw.png",
                  Inches(0.55), Inches(3.1), w=Inches(5.65))''',
'''    if (IMG / "gaw.png").exists():
        add_browser_frame(s, Inches(0.4), Inches(2.95), Inches(5.95), Inches(3.95),
                          img_path=IMG / "gaw.png", title="google.com/alerts")''')

    # Slide 13
    content = content.replace('''    if (IMG / "ga.png").exists():
        add_image(s, IMG / "ga.png", Inches(0.7), Inches(1.95), w=Inches(8))''',
'''    if (IMG / "ga.png").exists():
        add_browser_frame(s, Inches(0.6), Inches(1.95), Inches(8.2), Inches(4.7), img_path=IMG / "ga.png", title="dbm.soc.local/google_alerts")''')

    # Slide 14
    content = content.replace('''    if (IMG / "TIP.png").exists():
        add_rect(s, Inches(0.4), Inches(1.9), Inches(8.15), Inches(5.05),
                 fill=CARD_BG, line=BORDER_LINE, corner=True)
        add_image(s, IMG / "TIP.png",
                  Inches(0.55), Inches(2.05), w=Inches(7.85))''',
'''    if (IMG / "TIP.png").exists():
        add_browser_frame(s, Inches(0.4), Inches(1.9), Inches(8.15), Inches(5.05),
                          img_path=IMG / "TIP.png", title="dbm.soc.local/bi_pipeline")''')

    # Slide 15
    orig_s15 = '''        # screenshot
        img_path = IMG / img_name
        if img_path.exists():
            add_image(s, img_path, dx + Inches(0.2), dy + Inches(0.75),
                      w=dw - Inches(0.4))'''
    new_s15 = '''        # screenshot frame
        img_path = IMG / img_name
        if img_path.exists():
            # Create a minimalist chart frame inside the card
            add_browser_frame(s, dx + Inches(0.15), dy + Inches(0.75), dw - Inches(0.3), Inches(3.0),
                              img_path=img_path, title=img_name, border=BORDER_FAINT, fill=CARD_BG_2)'''
    content = content.replace(orig_s15, new_s15)

    # Slide 16
    content = content.replace('''    if (IMG / "collection.png").exists():
        add_rect(s, left_x - Inches(0.05), Inches(3.5), left_w + Inches(0.1),
                 Inches(2.5), fill=CARD_BG, line=BORDER_LINE, corner=True)
        add_image(s, IMG / "collection.png",
                  left_x + Inches(0.05), Inches(3.6), w=left_w - Inches(0.1))''',
'''    if (IMG / "collection.png").exists():
        add_browser_frame(s, left_x - Inches(0.05), Inches(3.5), left_w + Inches(0.1),
                          Inches(2.5), img_path=IMG / "collection.png", title="dbm.soc.local/runs")''')

    # Slide 18 Conclusion
    orig_s18 = """def slide_18_conclusion():
    s = prs.slides.add_slide(BLANK); add_bg(s)
    add_chrome(s, "Conclusion & perspectives", "Imane", 18)

    blocks = [
        ("Ce qu'on a réalisé",
         ["Plateforme multi-sources (GitHub, Telegram,\\nGoogle Alerts, BI CVE)",
          "Pipeline complet : collecte → restitution",
          "Architecture médaillon pour la BI CVE",
          "Dashboards Power BI interactifs"],
         "✓", ACCENT_GREEN),
        ("Ce qu'on a appris",
         ["La veille = processus méthodologique,\\npas une accumulation de logs",
          "Importance de la separation des responsabilités",
          "Detection policy comme garde-fou central",
          "Sources OSINT autorisées suffisantes"],
         "★", ACCENT_BLUE),
        ("Perspectives",
         ["Améliorer la corrélation inter-sources",
          "Automatiser la production de rapports",
          "Enrichir les indicateurs de risque",
          "Du pédagogique vers l'opérationnel"],
         "↗", ACCENT_AMBER),
    ]
    bw = Inches(4.05); bh = Inches(4.5); gap = Inches(0.15)
    total = bw * 3 + gap * 2
    bx0 = (SW - total) / 2; by = Inches(1.6)
    for i, (title, items, icon, color) in enumerate(blocks):
        bx = bx0 + i * (bw + gap)
        add_rect(s, bx, by, bw, bh, fill=CARD_BG, line=BORDER_LINE, corner=True)
        add_rect(s, bx, by, bw, Inches(0.08), fill=color)
        # icon
        add_text(s, bx + Inches(0.3), by + Inches(0.3), Inches(0.6), Inches(0.6),
                 icon, size=28, bold=True, color=color)
        add_text(s, bx + Inches(1.0), by + Inches(0.4), bw - Inches(1.2),
                 Inches(0.5), title, size=15, bold=True, color=TEXT_PRIMARY)
        # items
        iy = by + Inches(1.3)
        for it in items:
            dot = s.shapes.add_shape(MSO_SHAPE.OVAL, bx + Inches(0.35),
                                     iy + Inches(0.18), Inches(0.12), Inches(0.12))
            dot.line.fill.background(); dot.fill.solid()
            dot.fill.fore_color.rgb = color; dot.shadow.inherit = False
            add_text(s, bx + Inches(0.6), iy, bw - Inches(0.8), Inches(0.8),
                     it, size=11, color=TEXT_SEC, line_spacing=1.3)
            iy += Inches(0.78)

    # Final tagline
    add_text(s, Inches(0.7), Inches(6.5), Inches(12), Inches(0.5),
             "« Une chaîne de veille rigoureuse, défensive et exploitable, "
             "à partir de sources ouvertes et autorisées. »",
             size=13, italic=True, color=ACCENT_BLUE, align="center")"""

    new_s18 = """def slide_18_conclusion():
    s = prs.slides.add_slide(BLANK); add_bg(s)
    add_chrome(s, "Conclusion & perspectives", "Imane", 18)

    blocks = [
        ("ACHIEVEMENTS", "Ce qu'on a réalisé",
         ["Plateforme multi-sources (GitHub, Telegram,\\nGoogle Alerts, BI CVE)",
          "Pipeline complet : collecte → restitution",
          "Architecture médaillon pour la BI CVE",
          "Dashboards Power BI interactifs"],
         ACCENT_GREEN),
        ("LIMITS & LEARNINGS", "Ce qu'on a appris",
         ["La veille = processus méthodologique,\\npas une accumulation de logs",
          "Importance de la separation des responsabilités",
          "Detection policy comme garde-fou central",
          "Sources OSINT autorisées suffisantes"],
         ACCENT_BLUE),
        ("PERSPECTIVES", "Roadmap future",
         ["Améliorer la corrélation inter-sources",
          "Automatiser la production de rapports",
          "Enrichir les indicateurs de risque",
          "Du pédagogique vers l'opérationnel"],
         ACCENT_AMBER),
    ]
    bw = Inches(4.0); bh = Inches(4.2); gap = Inches(0.2)
    total = bw * 3 + gap * 2
    bx0 = (SW - total) / 2; by = Inches(1.8)
    for i, (subtitle, title, items, color) in enumerate(blocks):
        bx = bx0 + i * (bw + gap)
        # Soft sleek card
        add_rect(s, bx, by, bw, bh, fill=CARD_BG, line=BORDER_FAINT, corner=True)
        # Glowing accent dot
        dot = s.shapes.add_shape(MSO_SHAPE.OVAL, bx + Inches(0.3), by + Inches(0.3), Inches(0.15), Inches(0.15))
        dot.line.fill.background(); dot.fill.solid(); dot.fill.fore_color.rgb = color; dot.shadow.inherit = False
        
        add_text(s, bx + Inches(0.6), by + Inches(0.22), bw - Inches(0.8), Inches(0.3),
                 subtitle, size=10, bold=True, color=color, font="Consolas")
        add_text(s, bx + Inches(0.3), by + Inches(0.6), bw - Inches(0.6), Inches(0.5),
                 title, size=18, bold=True, color=TEXT_PRIMARY, font="Calibri Light")
                 
        add_line(s, bx + Inches(0.3), by + Inches(1.2), bx + Inches(1.5), by + Inches(1.2), color=BORDER_LINE, weight=1.5)
        
        iy = by + Inches(1.4)
        for it in items:
            chk = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, bx + Inches(0.35), iy + Inches(0.18), Inches(0.12), Inches(0.12))
            chk.line.fill.background(); chk.fill.solid(); chk.fill.fore_color.rgb = color; chk.shadow.inherit = False
            chk.adjustments[0] = 0.3
            
            add_text(s, bx + Inches(0.6), iy, bw - Inches(0.8), Inches(0.8),
                     it, size=11, color=TEXT_SEC, line_spacing=1.3)
            iy += Inches(0.7)

    # Final insight box
    add_rect(s, bx0, Inches(6.2), total, Inches(0.7), fill=CARD_BG_2, corner=True)
    add_rect(s, bx0, Inches(6.2), Inches(0.1), Inches(0.7), fill=ACCENT_VIOLET, corner=False)
    add_text(s, bx0, Inches(6.35), total, Inches(0.4),
             "Une chaîne de veille rigoureuse, défensive et exploitable, "
             "à partir de sources ouvertes et autorisées.",
             size=14, italic=True, color=TEXT_PRIMARY, align="center")"""
    content = content.replace(orig_s18, new_s18)

    p.write_text(content, encoding="utf-8")
    print("Done slides update")

if __name__ == "__main__":
    update_slides()
