"""
docs/generate_pdf.py

Enterprise System Documentation & PDF Generator for Continuity Guardian.
Generates a publication-grade PDF specification conforming to the standard of
ChitChatHire AI System Documentation.

Author: V.A. Sai Venkatesh
Platform: Continuity Guardian
"""

import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas
from PIL import Image as PILImage


class EnterpriseSpecCanvas(canvas.Canvas):
    """Canvas that implements a two-pass render to draw dynamic page totals, headers, and double borders."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_enterprise_decorations(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_enterprise_decorations(self, page_count):
        self.saveState()
        w, h = letter

        # Double Outer Enterprise Border
        self.setStrokeColor(colors.HexColor("#1E1B4B"))
        self.setLineWidth(1.5)
        self.rect(36, 36, w - 72, h - 72)
        self.setStrokeColor(colors.HexColor("#7C3AED"))
        self.setLineWidth(0.5)
        self.rect(39, 39, w - 78, h - 78)

        # Header on all pages > 1
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#1E1B4B"))
            self.drawString(50, h - 34, "Continuity Guardian — Complete Engineering Specification & System Documentation")
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawRightString(w - 50, h - 34, "Lead Architect: V.A. Sai Venkatesh")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(50, h - 38, w - 50, h - 38)

        # Footer on all pages > 1
        if self._pageNumber > 1:
            self.setFont("Helvetica", 8.5)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawString(50, 32, "CONFIDENTIAL & PROPRIETARY — Continuity Guardian Cinema Studio Edition v1.0")
            footer_text = f"Page {self._pageNumber} of {page_count}"
            self.drawRightString(w - 50, 32, footer_text)
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(50, 42, w - 50, 42)

        self.restoreState()


modules_continuity = [
    {
        "num": "Module 1",
        "title": "Autonomous Multi-Agent Architecture Topology",
        "img": "01_multi_agent_architecture_topology.png",
        "why": "Screenplays interweave fictional universe lore with real-world historical facts. Fictional lore lives strictly in the studio show bible, while real-world facts require live web grounding. The multi-agent pipeline routes claims to their specialized verification source concurrently via asyncio.gather().",
        "note_title": "Asynchronous Fan-Out / Fan-In Topology",
        "note_text": "The FactExtractor parses scene dialogue and action lines. Claims are bifurcated into 'internal' (Firestore) and 'real_world' (Parallel AI MCP), cutting analysis latency from O(N * T) serial delays to O(max(T_internal, T_real_world))."
    },
    {
        "num": "Module 2",
        "title": "Interactive OpenAPI Studio Developer Console (/docs)",
        "img": "02_api_developer_console_overview.png",
        "why": "Enterprise studio engineering teams, script supervisors, and third-party production tool developers (Final Draft, Movie Magic) require interactive, complete OpenAPI 3.1 specifications to inspect endpoints, schemas, and live curl requests.",
        "note_title": "Cinema Studio Dark Theme & Navigation",
        "note_text": "Features an obsidian studio palette (#08070d), responsive topbar with live port 8000 health indicator, direct web-app return button, and one-click switching between Swagger UI and ReDoc specifications."
    },
    {
        "num": "Module 3",
        "title": "Modular Subsystem Endpoints & OpenAPI 3.1 Registry",
        "img": "03_openapi_subsystems_and_endpoints.png",
        "why": "Organizes the platform into four distinct operational subsystems: Continuity Engine (core script analysis), Script Doctor (screenplay revision), Show Bible (Firestore canon database), and System & Health (liveness & readiness probes).",
        "note_title": "Interactive Endpoint Console Mechanics",
        "note_text": "Each endpoint includes pre-loaded Hollywood screenplay scenarios (Maya Vance, Daniel Vance, Detective Carter) with live 'Try it out' execution returning formatted JSON reports and confidence-ranked issues."
    },
    {
        "num": "Module 4",
        "title": "Google Cloud Firestore Show Bible & Canon Explorer",
        "img": "04_firestore_show_bible_canon_explorer.png",
        "why": "Preserves multi-season narrative continuity across changing writers and showrunners. Prevents lore fractures by keeping immutable character history, handedness, medical traits, and chronological timeline milestones in cloud storage.",
        "note_title": "Firestore Canon Schema & Indexing",
        "note_text": "Stored under the 'episodes' collection with array-contains-any indexing for character tokens. Features seamless automatic fallback to local seed canon if cloud connectivity is interrupted."
    },
    {
        "num": "Module 5",
        "title": "Script Studio Executive Brief & Canon Verification Suite",
        "img": "05_script_studio_executive_brief_and_canon_pass.png",
        "why": "Provides showrunners and script supervisors with an instant executive summary. Clean screenplays receive a 'Canon Certified — 100% Continuity Pass' badge, while contradicted scenes trigger line-numbered triage cards and one-click Script Doctor auto-rewrites.",
        "note_title": "Autonomous Script Doctor Integration",
        "note_text": "When contradictions are flagged, the Gemini 3.5 Script Doctor agent autonomously rewrites the scene in standard Hollywood format, resolving all lore breaks while faithfully preserving character cadence and subtext."
    }
]


def generate_enterprise_spec_pdf():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_path = os.path.join(base_dir, "ContinuityGuardian_System_Documentation.pdf")
    img_dir = os.path.join(base_dir, "images")

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        leftMargin=52,
        rightMargin=52,
        topMargin=50,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()

    # Custom Typography & Colors
    title_style = ParagraphStyle(
        'CoverTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=21,
        leading=26,
        textColor=colors.HexColor("#1E1B4B"),
        spaceAfter=8
    )

    cover_sub = ParagraphStyle(
        'CoverSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12
    )

    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#1E1B4B"),
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#7C3AED"),
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=9,
        leading=13.5,
        alignment=4,  # Justify
        textColor=colors.HexColor("#334155"),
        spaceAfter=6
    )

    code_style = ParagraphStyle(
        'CodeStyle',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7.5,
        leading=10.5,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=4
    )

    note_style = ParagraphStyle(
        'NoteText',
        parent=styles['Normal'],
        fontName='Courier-Oblique',
        fontSize=8,
        leading=11.5,
        textColor=colors.HexColor("#78350F")
    )

    def make_callout_box(title, text, bg="#FEF3C7", border="#F59E0B", title_color="#B45309"):
        content = [
            Paragraph(f"<b>★ {title} — V.A. Sai Venkatesh (Lead Architect)</b>", ParagraphStyle('NoteH', fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.HexColor(title_color))),
            Spacer(1, 2),
            Paragraph(text, note_style)
        ]
        t = Table([[content]], colWidths=[508])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(bg)),
            ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor(border)),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        return t

    story = []

    # =========================================================================
    # PAGE 1: COVER PAGE
    # =========================================================================
    story.append(Spacer(1, 10))
    logo_path = os.path.join(img_dir, "project_logo.png")
    if os.path.exists(logo_path):
        story.append(RLImage(logo_path, width=70, height=70))
        story.append(Spacer(1, 10))

    story.append(Paragraph("Continuity Guardian — Complete Engineering Specification &amp; System Documentation", title_style))
    story.append(Paragraph("Autonomous Multi-Agent Cinema Script Continuity Supervision, Narrative Canon Verification &amp; Screenplay Doctor Engine", cover_sub))
    story.append(Spacer(1, 10))

    meta_table_data = [
        [Paragraph("<b>Lead Engineer &amp; Architect:</b>", body_style), Paragraph("<b>V.A. SAI VENKATESH</b>", body_style)],
        [Paragraph("<b>System Architecture:</b>", body_style), Paragraph("Google Gemini 3.5 Flash, Google ADK, Cloud Firestore, Parallel AI MCP, FastAPI Async", body_style)],
        [Paragraph("<b>Production Web Stack:</b>", body_style), Paragraph("Hollywood Studio Dark UI/UX, Screenplay Slate Editor, Swagger UI, ReDoc", body_style)],
        [Paragraph("<b>Target Domain:</b>", body_style), Paragraph("Prestige Television Series &amp; Feature Film Screenwriting Pre-Production", body_style)],
        [Paragraph("<b>Document Classification:</b>", body_style), Paragraph("Enterprise Production Manual v1.0 (September 2026)", body_style)],
    ]
    t_meta = Table(meta_table_data, colWidths=[150, 358])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 12))

    story.append(make_callout_box(
        "LEAD ARCHITECT SYSTEM VISION",
        "\"Traditional Hollywood script supervision is a grueling, paper-heavy manual discipline. A single contradiction missed during pre-production can trigger seven-figure reshoots once principal photography concludes. Continuity Guardian unifies 5 specialized AI agents into an asynchronous fan-out / fan-in topology that grounds screenplay beats against immutable Firestore canon and live web reality with sub-second retrieval and Bayesian confidence scoring.\""
    ))
    story.append(Spacer(1, 12))

    # Executive Overview
    story.append(Paragraph("Executive Overview: The Hollywood Continuity Challenge", h1_style))
    story.append(Paragraph(
        "In film and television production, narrative continuity errors cost studios hundreds of thousands to millions of dollars in emergency script revisions, delayed shoots, and expensive reshoots. Fictional lore fractures (characters referencing deceased relatives as living, misremembering past events) and timeline collisions (historical dates, medical realities) destroy audience immersion.",
        body_style
    ))
    story.append(Paragraph(
        "Continuity Guardian eliminates these vulnerabilities by deploying an autonomous multi-agent network that extracts declarative claims from screenplay dialogue and action lines, cross-references internal show bible canon in Google Cloud Firestore, and conducts real-time web fact-checking via Parallel AI MCP in under 5 seconds.",
        body_style
    ))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: ARCHITECTURE & COMPUTER SCIENCE FOUNDATIONS
    # =========================================================================
    story.append(Paragraph("System Architecture &amp; Computer Science Foundations", h1_style))
    story.append(Paragraph(
        "Continuity Guardian is organized as a 4-tier distributed system with strict boundary separation between Presentation, API Routing, Agent Orchestration, and Data/External Grounding layers.",
        body_style
    ))

    cs_table_data = [
        [Paragraph("<b>Computer Science Pattern</b>", body_style), Paragraph("<b>Implementation &amp; File Location</b>", body_style), Paragraph("<b>Engineering Rationale</b>", body_style)],
        [
            Paragraph("<b>Multi-Agent Orchestrator</b>", body_style),
            Paragraph("<code>agent/pipeline.py</code> (Google ADK Native)", code_style),
            Paragraph("Decouples claim extraction, domain checking, executive reporting, and script repair into isolated testable components.", body_style)
        ],
        [
            Paragraph("<b>Async Parallel Fan-Out</b>", body_style),
            Paragraph("<code>asyncio.gather()</code> in Pipeline", code_style),
            Paragraph("Bifurcates internal canon checking and real-world web search concurrently, cutting overall pipeline latency by over 50%.", body_style)
        ],
        [
            Paragraph("<b>Repository Pattern</b>", body_style),
            Paragraph("<code>agent/repository.py</code>", code_style),
            Paragraph("Encapsulates Cloud Firestore operations with automated fallback to <code>data/seed_episodes.json</code> for 100% offline uptime.", body_style)
        ],
        [
            Paragraph("<b>Deterministic Memoization</b>", body_style),
            Paragraph("<code>agent/checkers.py</code> (SHA-256 Hash)", code_style),
            Paragraph("Caches web fact-checking results for 6 hours, eliminating redundant queries and preserving Parallel AI MCP search quota.", body_style)
        ],
        [
            Paragraph("<b>Bayesian Ranking</b>", body_style),
            Paragraph("<code>agent/report_builder.py</code>", code_style),
            Paragraph("Calculates confidence scores (0.00 to 1.00) and sorts critical lore breaks to the top of the executive brief.", body_style)
        ],
    ]
    t_cs = Table(cs_table_data, colWidths=[120, 150, 238])
    t_cs.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E1B4B")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_cs)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Claim Classification Matrix", h2_style))
    matrix_data = [
        [Paragraph("<b>Claim Type</b>", body_style), Paragraph("<b>Scope &amp; Source of Truth</b>", body_style), Paragraph("<b>Screenplay Demonstration Example</b>", body_style), Paragraph("<b>Handling Agent</b>", body_style)],
        [
            Paragraph("<b>internal</b>", body_style),
            Paragraph("Narrative canon stored in Cloud Firestore Show Bible", body_style),
            Paragraph("<i>'Daniel called me from Chicago; he is alive!'</i> (Contradicts S01E01 car crash death in 2021)", body_style),
            Paragraph("<code>InternalChecker</code> (Firestore + Gemini 3.5)", code_style)
        ],
        [
            Paragraph("<b>real_world</b>", body_style),
            Paragraph("External science, history, geography via live web", body_style),
            Paragraph("<i>'Alexander Fleming gave him penicillin in 1985.'</i> (Penicillin was discovered in 1928)", body_style),
            Paragraph("<code>RealWorldChecker</code> (Parallel AI MCP + Gemini)", code_style)
        ]
    ]
    t_matrix = Table(matrix_data, colWidths=[65, 135, 185, 123])
    t_matrix.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#7C3AED")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_matrix)

    story.append(PageBreak())

    # =========================================================================
    # MODULE-BY-MODULE VISUAL SPECIFICATIONS (PAGES 3 - 7)
    # =========================================================================
    for idx, mod in enumerate(modules_continuity, start=1):
        story.append(Paragraph(f"Part I.{idx}: {mod['title']}", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#7C3AED"), spaceBefore=2, spaceAfter=8))

        # Screenshot Image
        img_path = os.path.join(img_dir, mod["img"])
        if os.path.exists(img_path):
            try:
                with PILImage.open(img_path) as im:
                    orig_w, orig_h = im.size
                target_w = 508
                aspect = orig_h / orig_w
                target_h = min(target_w * aspect, 220)  # constrain height so content fits page
                story.append(RLImage(img_path, width=target_w, height=target_h))
                story.append(Spacer(1, 8))
            except Exception as e:
                story.append(Paragraph(f"<i>[Screenshot placeholder: {mod['img']} - {e}]</i>", body_style))

        # Callout Note
        story.append(make_callout_box(mod["note_title"], mod["note_text"], bg="#F5F3FF", border="#8B5CF6", title_color="#6D28D9"))
        story.append(Spacer(1, 8))

        # Why It Is Needed
        story.append(Paragraph("<b>Why It Is Needed:</b>", h2_style))
        story.append(Paragraph(mod["why"], body_style))

        # How to Use & Operations
        story.append(Paragraph("<b>Operational Procedures &amp; Workflow:</b>", h2_style))
        if idx == 1:
            story.append(Paragraph(
                "1. Submit raw screenplay text via <code>POST /check-episode</code>.<br/>"
                "2. FactExtractor identifies named character entities, timeline markers, and physical action assertions.<br/>"
                "3. Dual checkers evaluate internal canon and external reality concurrently via <code>asyncio.gather</code>.<br/>"
                "4. ReportBuilder formats Bayesian confidence-ranked results for producer review.",
                body_style
            ))
        elif idx == 2:
            story.append(Paragraph(
                "1. Navigate to <code>http://localhost:8000/docs</code> in any modern browser.<br/>"
                "2. Inspect the persistent studio topbar: check the green 'API Online' telemetry status.<br/>"
                "3. Toggle between interactive Swagger UI and high-density ReDoc specifications.<br/>"
                "4. Review the multi-agent topology, curl quickstarts, and HTTP error code dictionary.",
                body_style
            ))
        elif idx == 3:
            story.append(Paragraph(
                "1. Expand an endpoint block (e.g., <code>POST /check-episode</code> or <code>POST /rewrite-script</code>).<br/>"
                "2. Click 'Try it out' to populate realistic Hollywood scene payloads (S01E04 demo).<br/>"
                "3. Click the violet gradient 'Execute' button to dispatch the request.<br/>"
                "4. Inspect response bodies, HTTP status codes, and generated curl syntax.",
                body_style
            ))
        elif idx == 4:
            story.append(Paragraph(
                "1. Click 'Show Bible' in the web studio header to launch the Firestore Canon Explorer.<br/>"
                "2. Review introduced character lists (Maya, Daniel, Carter, Alex) and established facts.<br/>"
                "3. Inspect physical canon: Maya's left-handedness, Detective Carter's aquaphobia, and penicillin allergies.<br/>"
                "4. Ensure newly written scenes align strictly with established chronological lore milestones.",
                body_style
            ))
        elif idx == 5:
            story.append(Paragraph(
                "1. Paste screenplay scene into the line-numbered slate editor, or click pre-calibrated Demo Chips.<br/>"
                "2. Click 'Run Continuity Check' to trigger the 5-agent verification network.<br/>"
                "3. If contradictions are found, review the Script Doctor panel and click 'Auto-Rewrite with Script Doctor'.<br/>"
                "4. Click 'Export Studio Markdown' to download a publication-ready editorial brief for the production room.",
                body_style
            ))

        story.append(PageBreak())

    # =========================================================================
    # PART II: REST API SPECIFICATION
    # =========================================================================
    story.append(Paragraph("Part II: Complete REST API Specification", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#7C3AED"), spaceBefore=2, spaceAfter=8))

    story.append(Paragraph("Core Production Endpoints", h2_style))
    api_table_data = [
        [Paragraph("<b>Method &amp; Path</b>", body_style), Paragraph("<b>Subsystem</b>", body_style), Paragraph("<b>Description &amp; Operation</b>", body_style)],
        [
            Paragraph("<b>POST /check-episode</b>", body_style),
            Paragraph("Continuity Engine", body_style),
            Paragraph("Runs full 5-agent pipeline; extracts claims, cross-references Firestore &amp; Parallel AI, returns confidence-ranked report.", body_style)
        ],
        [
            Paragraph("<b>POST /rewrite-script</b>", body_style),
            Paragraph("Script Doctor", body_style),
            Paragraph("Autonomously rewrites scenes to eliminate contradictions while faithfully preserving character cadence and sluglines.", body_style)
        ],
        [
            Paragraph("<b>GET /show-bible</b>", body_style),
            Paragraph("Show Bible", body_style),
            Paragraph("Retrieves complete multi-season canon records from Cloud Firestore (characters, traits, timeline events).", body_style)
        ],
        [
            Paragraph("<b>GET /episodes</b>", body_style),
            Paragraph("Show Bible", body_style),
            Paragraph("Returns lightweight registry of registered episode IDs and dates added for UI selector dropdowns.", body_style)
        ],
        [
            Paragraph("<b>GET /health</b>", body_style),
            Paragraph("System &amp; Health", body_style),
            Paragraph("Deployment readiness probe for Cloud Run, Kubernetes, and Hugging Face Spaces. Returns <code>{\"status\": \"ok\"}</code>.", body_style)
        ],
        [
            Paragraph("<b>GET /</b>", body_style),
            Paragraph("System &amp; Health", body_style),
            Paragraph("Root service discovery catalog listing active engine version, database metadata, and endpoint map.", body_style)
        ],
    ]
    t_api = Table(api_table_data, colWidths=[120, 95, 293])
    t_api.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E1B4B")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_api)
    story.append(Spacer(1, 10))

    story.append(Paragraph("HTTP Status Code &amp; Resilience Dictionary", h2_style))
    status_data = [
        [Paragraph("<b>Status Code</b>", body_style), Paragraph("<b>Condition &amp; Cause</b>", body_style), Paragraph("<b>Platform Resolution &amp; Handling</b>", body_style)],
        [
            Paragraph("<b>200 OK</b>", body_style),
            Paragraph("Successful pipeline analysis, revision, or data retrieval", body_style),
            Paragraph("Returns structured JSON payload with confidence ratings.", body_style)
        ],
        [
            Paragraph("<b>422 Unprocessable</b>", body_style),
            Paragraph("Script length &lt; 20 characters or malformed JSON payload", body_style),
            Paragraph("FastAPI returns Pydantic validation error with descriptive message.", body_style)
        ],
        [
            Paragraph("<b>500 Server Error</b>", body_style),
            Paragraph("Missing <code>GEMINI_API_KEY</code> or invalid configuration", body_style),
            Paragraph("Surfaces clear error message instructing operator to verify environment.", body_style)
        ],
        [
            Paragraph("<b>503 Unavailable</b>", body_style),
            Paragraph("Firestore database timeout or transient network disruption", body_style),
            Paragraph("System auto-falls back to <code>data/seed_episodes.json</code> seed records.", body_style)
        ]
    ]
    t_status = Table(status_data, colWidths=[85, 170, 253])
    t_status.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#06B6D4")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_status)

    story.append(PageBreak())

    # =========================================================================
    # PART III: CLOUD FIRESTORE DATA ARCHITECTURE & DEPLOYMENT
    # =========================================================================
    story.append(Paragraph("Part III: Cloud Firestore Data Architecture &amp; Deployment", h1_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#7C3AED"), spaceBefore=2, spaceAfter=8))

    story.append(Paragraph("Firestore Schema: 'episodes' Collection", h2_style))
    schema_data = [
        [Paragraph("<b>Field Name</b>", body_style), Paragraph("<b>Data Type</b>", body_style), Paragraph("<b>Description &amp; Canonical Role</b>", body_style), Paragraph("<b>Indexing Rule</b>", body_style)],
        [
            Paragraph("<code>episode_id</code>", code_style),
            Paragraph("string", body_style),
            Paragraph("Unique identifier (e.g., 's01e01', 's01e02')", body_style),
            Paragraph("Primary document key", body_style)
        ],
        [
            Paragraph("<code>characters</code>", code_style),
            Paragraph("array&lt;string&gt;", body_style),
            Paragraph("Dramatis personae introduced in this episode", body_style),
            Paragraph("<code>array-contains-any</code> index", code_style)
        ],
        [
            Paragraph("<code>key_facts</code>", code_style),
            Paragraph("array&lt;string&gt;", body_style),
            Paragraph("Irrevocable narrative milestones established", body_style),
            Paragraph("Full-text token parsing", body_style)
        ],
        [
            Paragraph("<code>timeline</code>", code_style),
            Paragraph("map&lt;str, str&gt;", body_style),
            Paragraph("Year-to-event canonical timeline mappings", body_style),
            Paragraph("Standard map indexing", body_style)
        ],
        [
            Paragraph("<code>established_traits</code>", code_style),
            Paragraph("map&lt;str, str&gt;", body_style),
            Paragraph("Character allergies, handedness, phobias", body_style),
            Paragraph("Entity-attribute lookup", body_style)
        ],
        [
            Paragraph("<code>date_added</code>", code_style),
            Paragraph("string", body_style),
            Paragraph("ISO 8601 creation timestamp", body_style),
            Paragraph("Ascending sort index", body_style)
        ]
    ]
    t_schema = Table(schema_data, colWidths=[95, 75, 230, 108])
    t_schema.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#10B981")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_schema)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Dual Production Deployment Architecture", h2_style))
    story.append(Paragraph(
        "<b>Option A — Google Cloud Run (Containerized Microservice):</b><br/>"
        "• Containerized via multi-stage Dockerfile based on <code>python:3.13-slim</code>.<br/>"
        "• Dynamically binds to the <code>$PORT</code> environment variable required by Cloud Run.<br/>"
        "• API keys (<code>GEMINI_API_KEY</code>, <code>PARALLEL_API_KEY</code>, <code>FIREBASE_PROJECT_ID</code>) mounted as Cloud Run Secrets.<br/>"
        "• Runs 100% within Google Cloud Free Tier limits ($0 monthly operational cost).",
        body_style
    ))
    story.append(Paragraph(
        "<b>Option B — Hugging Face Spaces (Zero-Card Docker Space):</b><br/>"
        "• Direct Git push to Hugging Face Spaces Docker runtime.<br/>"
        "• No billing card verification required.<br/>"
        "• Respects default port 7860 with secrets configured via Space Settings.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Frontend CDN Deployment (Vercel / GitHub Pages):</b><br/>"
        "• Zero-configuration edge hosting via <code>vercel.json</code>.<br/>"
        "• Static assets served with sub-50ms global CDN latency, proxying API requests to the active backend.",
        body_style
    ))
    story.append(Spacer(1, 10))

    story.append(make_callout_box(
        "ARCHITECTURAL SIGN-OFF",
        "\"Continuity Guardian represents a complete, deterministic engineering solution for cinema pre-production. By fusing Google Gemini 3.5 reasoning, Google ADK multi-agent orchestration, Cloud Firestore canon persistence, and Parallel AI live web grounding, the platform safeguards narrative integrity and prevents reshoots before the cameras roll.\""
    ))

    # Build PDF
    doc.build(story, canvasmaker=EnterpriseSpecCanvas)
    print(f"Successfully generated Enterprise Specification PDF: {pdf_path}")


if __name__ == "__main__":
    generate_enterprise_spec_pdf()
