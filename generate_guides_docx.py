"""
Générateur complet de documentation professionnelle Word (.docx) pour Venus Luna.
Produit :
1. docs/guides/guide_administrateur_venus_luna.docx
2. docs/guides/guide_apprenant_venus_luna.docx
"""

import os
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "docs" / "guides"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Charte graphique Venus Luna
COLOR_EMERAUDE = RGBColor(28, 104, 59)      # #1C683B
COLOR_OR = RGBColor(212, 175, 55)          # #D4AF37
COLOR_DARK_TEXT = RGBColor(45, 55, 72)     # #2D3748
COLOR_MUTED = RGBColor(113, 128, 150)      # #718096

HEX_EMERAUDE = "1C683B"
HEX_EMERAUDE_LIGHT = "F0F7F4"
HEX_OR = "D4AF37"
HEX_ALERT_BG = "FFFBEB"
HEX_ALERT_BORDER = "F59E0B"
HEX_GREY_LIGHT = "F8FAFC"
HEX_BORDER = "CBD5E1"


def set_cell_background(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=140, bottom=140, left=180, right=180):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'''
        <w:tcMar {nsdecls("w")}>
            <w:top w:w="{top}" w:type="dxa"/>
            <w:bottom w:w="{bottom}" w:type="dxa"/>
            <w:left w:w="{left}" w:type="dxa"/>
            <w:right w:w="{right}" w:type="dxa"/>
        </w:tcMar>
    ''')
    tcPr.append(tcMar)


def add_callout(doc, text, title="CONSEIL PRATIQUE", callout_type="tip"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    tbl.columns[0].width = Inches(6.5)

    cell = tbl.cell(0, 0)
    bg_color = HEX_EMERAUDE_LIGHT if callout_type == "tip" else HEX_ALERT_BG
    border_color = HEX_EMERAUDE if callout_type == "tip" else HEX_ALERT_BORDER
    title_color = COLOR_EMERAUDE if callout_type == "tip" else RGBColor(180, 83, 9)

    set_cell_background(cell, bg_color)
    set_cell_margins(cell, top=160, bottom=160, left=220, right=200)

    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = parse_xml(f'''
        <w:tcBorders {nsdecls("w")}>
            <w:top w:val="none"/>
            <w:left w:val="single" w:sz="36" w:space="0" w:color="{border_color}"/>
            <w:bottom w:val="none"/>
            <w:right w:val="none"/>
        </w:tcBorders>
    ''')
    tcPr.append(tcBorders)

    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(3)
    p.add_run("💡 " if callout_type == "tip" else "⚠️ ")
    run_title = p.add_run(f"{title}\n")
    run_title.bold = True
    run_title.font.size = Pt(10)
    run_title.font.color.rgb = title_color

    run_text = p.add_run(text)
    run_text.font.size = Pt(9.5)
    run_text.font.color.rgb = COLOR_DARK_TEXT

    p_after = doc.add_paragraph()
    p_after.paragraph_format.space_after = Pt(2)


def add_screenshot_placeholder(doc, number, title, path_desc, elements_desc):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    tbl.columns[0].width = Inches(6.5)

    cell = tbl.cell(0, 0)
    set_cell_background(cell, HEX_GREY_LIGHT)
    set_cell_margins(cell, top=160, bottom=160, left=200, right=200)

    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = parse_xml(f'''
        <w:tcBorders {nsdecls("w")}>
            <w:top w:val="single" w:sz="8" w:space="0" w:color="{HEX_BORDER}"/>
            <w:left w:val="single" w:sz="24" w:space="0" w:color="{HEX_OR}"/>
            <w:bottom w:val="single" w:sz="8" w:space="0" w:color="{HEX_BORDER}"/>
            <w:right w:val="single" w:sz="8" w:space="0" w:color="{HEX_BORDER}"/>
        </w:tcBorders>
    ''')
    tcPr.append(tcBorders)

    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)

    r_tag = p.add_run(f"📸 EMPLACEMENT VISUEL RÉEL — CAPTURE D'ÉCRAN N°{number}\n")
    r_tag.bold = True
    r_tag.font.size = Pt(8.5)
    r_tag.font.color.rgb = COLOR_OR

    r_title = p.add_run(f"{title}\n")
    r_title.bold = True
    r_title.font.size = Pt(10.5)
    r_title.font.color.rgb = COLOR_EMERAUDE

    r_path = p.add_run(f"📍 Emplacement dans l'application : {path_desc}\n")
    r_path.italic = True
    r_path.font.size = Pt(8.5)
    r_path.font.color.rgb = COLOR_MUTED

    r_el = p.add_run(f"🔍 Éléments clés identifiés : {elements_desc}\n")
    r_el.font.size = Pt(8.5)
    r_el.font.color.rgb = COLOR_DARK_TEXT

    r_note = p.add_run("ℹ️ Note de conformité : Emplacement réservé pour insertion de capture sans données confidentielles.")
    r_note.font.size = Pt(8)
    r_note.font.color.rgb = COLOR_MUTED

    p_after = doc.add_paragraph()
    p_after.paragraph_format.space_after = Pt(2)


def style_heading_1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(13.5)
    run.font.color.rgb = COLOR_EMERAUDE
    return p


def style_heading_2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(11)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(11.5)
    run.font.color.rgb = COLOR_OR
    return p


def style_heading_3(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(10)
    run.font.color.rgb = COLOR_DARK_TEXT
    return p


def style_paragraph(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(text)
    run.font.size = Pt(9.5)
    run.font.color.rgb = COLOR_DARK_TEXT
    return p


def style_bullet(doc, text, bold_prefix=""):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.left_indent = Inches(0.2)
    p.paragraph_format.line_spacing = 1.15
    r_bullet = p.add_run("• ")
    r_bullet.bold = True
    r_bullet.font.color.rgb = COLOR_EMERAUDE
    if bold_prefix:
        r_pre = p.add_run(bold_prefix + " ")
        r_pre.bold = True
        r_pre.font.size = Pt(9.5)
        r_pre.font.color.rgb = COLOR_DARK_TEXT
    r_txt = p.add_run(text)
    r_txt.font.size = Pt(9.5)
    r_txt.font.color.rgb = COLOR_DARK_TEXT
    return p


def create_table(doc, headers, data):
    tbl = doc.add_table(rows=len(data) + 1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False

    hdr_cells = tbl.rows[0].cells
    for i, h_text in enumerate(headers):
        hdr_cells[i].text = h_text
        set_cell_background(hdr_cells[i], HEX_EMERAUDE)
        set_cell_margins(hdr_cells[i], top=100, bottom=100, left=120, right=120)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for run in p.runs:
            run.bold = True
            run.font.size = Pt(9)
            run.font.color.rgb = RGBColor(255, 255, 255)

    for r_idx, row_data in enumerate(data):
        row_cells = tbl.rows[r_idx + 1].cells
        bg_col = HEX_GREY_LIGHT if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, cell_value in enumerate(row_data):
            row_cells[c_idx].text = cell_value
            set_cell_background(row_cells[c_idx], bg_col)
            set_cell_margins(row_cells[c_idx], top=80, bottom=80, left=120, right=120)
            p = row_cells[c_idx].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for run in p.runs:
                run.font.size = Pt(8.5)
                run.font.color.rgb = COLOR_DARK_TEXT

    p_after = doc.add_paragraph()
    p_after.paragraph_format.space_after = Pt(4)


def add_cover_page(doc, title, subtitle, target_audience, doc_version="1.0.0"):
    p_top_space = doc.add_paragraph()
    p_top_space.paragraph_format.space_before = Pt(36)

    # Organisation
    p_org = doc.add_paragraph()
    p_org.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_org = p_org.add_run("INSTITUT SPIRITUEL & BIEN-ÊTRE\nVENUS LUNA")
    r_org.bold = True
    r_org.font.size = Pt(14)
    r_org.font.color.rgb = COLOR_OR

    # Ligne décorative dorée
    p_line = doc.add_paragraph()
    p_line.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_line = p_line.add_run("❖  •  ━━━━━━━━━━━━━━━━━━━━━━━  •  ❖")
    r_line.font.color.rgb = COLOR_OR
    r_line.font.size = Pt(11)

    p_mid_space = doc.add_paragraph()
    p_mid_space.paragraph_format.space_before = Pt(40)

    # Grand Titre
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_after = Pt(12)
    r_title = p_title.add_run(title)
    r_title.bold = True
    r_title.font.size = Pt(22)
    r_title.font.color.rgb = COLOR_EMERAUDE

    # Sous-titre
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_after = Pt(30)
    r_sub = p_sub.add_run(subtitle)
    r_sub.font.size = Pt(12)
    r_sub.font.color.rgb = COLOR_DARK_TEXT

    # Encadré d'informations de couverture
    tbl_meta = doc.add_table(rows=4, cols=2)
    tbl_meta.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_meta.columns[0].width = Inches(2.2)
    tbl_meta.columns[1].width = Inches(4.0)

    meta_rows = [
        ("Public Cible :", target_audience),
        ("Version du Document :", f"Version {doc_version} (Production)"),
        ("Date de Publication :", "Novembre 2026"),
        ("Plateforme :", "Venus Luna Django E-Commerce & LMS"),
    ]

    for idx, (label, val) in enumerate(meta_rows):
        c0 = tbl_meta.cell(idx, 0)
        c1 = tbl_meta.cell(idx, 1)
        c0.text = label
        c1.text = val
        set_cell_background(c0, HEX_EMERAUDE_LIGHT)
        set_cell_background(c1, "FFFFFF")
        set_cell_margins(c0, top=80, bottom=80, left=100, right=100)
        set_cell_margins(c1, top=80, bottom=80, left=100, right=100)
        p0 = c0.paragraphs[0]
        p1 = c1.paragraphs[0]
        p0.runs[0].bold = True
        p0.runs[0].font.size = Pt(9)
        p0.runs[0].font.color.rgb = COLOR_EMERAUDE
        p1.runs[0].font.size = Pt(9)
        p1.runs[0].font.color.rgb = COLOR_DARK_TEXT

    p_bottom = doc.add_paragraph()
    p_bottom.paragraph_format.space_before = Pt(90)
    p_bottom.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_bot = p_bottom.add_run("Documentation Officielle d'Exploitation — Vénus-Luna Lomé (Togo)")
    r_bot.font.size = Pt(8.5)
    r_bot.font.color.rgb = COLOR_MUTED

    doc.add_page_break()


# ==============================================================================
# 1. GÉNÉRATION DU GUIDE ADMINISTRATEUR
# ==============================================================================

def generate_admin_guide():
    print("⏳ Génération du Guide Administrateur DOCX...")
    doc = Document()

    # Configuration des marges
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)
        
        # En-tête
        header = section.header
        p_head = header.paragraphs[0]
        p_head.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r_head = p_head.add_run("VENUS LUNA ACADEMY  |  GUIDE D'ADMINISTRATION")
        r_head.font.size = Pt(8)
        r_head.font.color.rgb = COLOR_MUTED

        # Pied de page
        footer = section.footer
        p_foot = footer.paragraphs[0]
        p_foot.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r_foot = p_foot.add_run("Venus Luna — Guide d'Administration et de Gestion des Formations  |  v1.0.0")
        r_foot.font.size = Pt(8)
        r_foot.font.color.rgb = COLOR_MUTED

    # Page de couverture
    add_cover_page(
        doc,
        title="GUIDE D'ADMINISTRATION ET DE GESTION DES FORMATIONS",
        subtitle="Manuel Complet d'Exploitation et d'Ingénierie Pédagogique",
        target_audience="Administrateurs système, gestionnaires e-commerce, coordinateurs pédagogiques et formateurs habilités",
        doc_version="1.0.0",
    )

    # Sommaire
    style_heading_1(doc, "TABLE DES MATIÈRES")
    sommaire_items = [
        "1. Présentation générale du LMS Venus Luna",
        "2. Connexion à l'espace d'administration",
        "3. Présentation du tableau de bord d'administration",
        "4. Gestion des catégories de formation",
        "5. Gestion des formateurs et des comptes instructeurs",
        "6. Création d'une formation (Cycle de vie & Statuts)",
        "7. Configuration des informations générales et pédagogiques",
        "8. Ajout et optimisation de l'image de couverture",
        "9. Configuration des tarifs et modalités d'accès",
        "10. Organisation et structuration des modules",
        "11. Création et paramétrage des leçons",
        "12. Ajout de vidéos et ressources pédagogiques jointes",
        "13. Création des quiz d'évaluation",
        "14. Configuration des questions, options et barèmes",
        "15. Gestion administrative des inscriptions (Enrollments)",
        "16. Gestion des apprenants et profils utilisateurs",
        "17. Gestion des formations gratuites",
        "18. Gestion des formations payantes et commandes CashPay",
        "19. Suivi de progression des apprenants",
        "20. Configuration, délivrance et vérification des certificats",
        "21. Publication, modification et archivage des cours",
        "22. Bonnes pratiques de gestion et recommandations éditoriales",
        "23. Exercice pratique pas-à-pas : Création intégrale d'une formation certifiante",
        "24. Fiches mémo et guide de résolution des erreurs courantes",
    ]
    for item in sommaire_items:
        style_bullet(doc, item)

    doc.add_page_break()

    # 1. Présentation
    style_heading_1(doc, "1. Présentation Générale du LMS Venus Luna")
    style_paragraph(doc, "Le module LMS (Learning Management System) de Venus Luna est une extension native intégrée à la plateforme e-commerce Django. Il permet à l'Académie Venus Luna de dispenser des formations spirituelles et bien-être de haute qualité (lithothérapie, méditation, chakras, rituels sacrés) avec un suivi complet des inscriptions, de la progression et de la certification.")
    style_bullet(doc, "Classement thématique doté d'icônes FontAwesome et d'un ordre d'affichage sur mesure.", "CourseCategory (Catégorie) :")
    style_bullet(doc, "Programme complet avec niveau, durée estimée, prix (FCFA), objectifs pédagogiques et certification.", "Course (Formation) :")
    style_bullet(doc, "Chapitre thématique regroupant une séquence ordonnée de leçons.", "CourseModule (Module) :")
    style_bullet(doc, "Unité pédagogique multimédia (vidéo YouTube/Vimeo/MP4, document PDF, notes de cours ou quiz).", "Lesson (Leçon) :")
    style_bullet(doc, "Droit d'accès accordé à un apprenant avec suivi de complétion et historique.", "Enrollment (Inscription) :")
    style_bullet(doc, "Diplôme officiel vectoriel A4 paysage muni d'un code unique VL-... et d'un QR code de vérification.", "Certificate (Certificat) :")

    # 2. Connexion
    style_heading_1(doc, "2. Connexion à l'Espace d'Administration")
    style_paragraph(doc, "L'accès à l'interface administrative nécessite un compte disposant des droits 'Statut équipe' (is_staff=True).")
    style_bullet(doc, "Ouvrez votre navigateur et saisissez l'URL d'administration : https://venus-luna.com/admin/ (ou http://127.0.0.1:8000/admin/ en local).", "Étape 1 :")
    style_bullet(doc, "Renseignez votre nom d'utilisateur et votre mot de passe confidentiel.", "Étape 2 :")
    style_bullet(doc, "Cliquez sur 'Se connecter' pour valider votre authentification.", "Étape 3 :")
    add_screenshot_placeholder(doc, "1", "Écran de connexion à l'administration Django", "/admin/login/", "Formulaire d'authentification avec champs 'Nom d'utilisateur', 'Mot de passe' et bouton de connexion.")
    add_callout(doc, "Ne mémorisez jamais vos identifiants sur un poste partagé. Déconnectez-vous systématiquement en fin d'activité.", "SÉCURITÉ DES ACCÈS", "warning")

    # 3. Dashboard
    style_heading_1(doc, "3. Présentation du Tableau de Bord d'Administration")
    style_paragraph(doc, "Sur la page principale de l'administration, descendez jusqu'au bloc intitulé 'COURSES' (ou 'FORMATIONS'). Ce bloc constitue votre console de pilotage pédagogique et regroupe l'accès aux catégories, formations, modules, leçons, inscriptions, quiz et certificats.")
    add_screenshot_placeholder(doc, "2", "Tableau de bord - Section COURSES", "/admin/", "Liste des modèles Courses avec compteurs et boutons d'action '+ Ajouter'.")

    # 4. Catégories
    style_heading_1(doc, "4. Gestion des Catégories de Formation")
    style_paragraph(doc, "Les catégories structurent l'offre de formation sur le catalogue public (ex: Lithothérapie, Méditation, Rituels).")
    style_bullet(doc, "Organiser et classifier les formations par pôle thématique.", "Objectif :")
    style_bullet(doc, "Accueil Admin > Courses > Catégories de formation > + Ajouter.", "Chemin d'accès :")
    style_bullet(doc, "Nom de la catégorie (ex: 'Lithothérapie & Cristaux').", "Champ 1 :")
    style_bullet(doc, "Slug (laisser vide pour génération automatique).", "Champ 2 :")
    style_bullet(doc, "Icône FontAwesome (ex: 'fa-gem', 'fa-spa', 'fa-moon', 'fa-leaf').", "Champ 3 :")
    style_bullet(doc, "Ordre d'affichage (entier positif pour déterminer la position sur le site).", "Champ 4 :")
    add_screenshot_placeholder(doc, "3", "Formulaire d'ajout d'une catégorie", "/admin/courses/coursecategory/add/", "Champs Nom, Slug, Description, Icône FontAwesome et Ordre d'affichage.")

    # 5. Formateurs
    style_heading_1(doc, "5. Gestion des Formateurs et Comptes Instructeurs")
    style_paragraph(doc, "Pour habiliter un formateur, créez ou modifiez son compte dans 'Utilisateurs' : cochez 'Statut équipe' et rattachez-le au groupe 'Formateurs'. Grâce au cloisonnement de sécurité de Venus Luna, un formateur rattaché à ce groupe ne verra dans l'administration que ses propres formations.")
    add_callout(doc, "Veillez à renseigner le prénom et le nom de l'instructeur dans sa fiche utilisateur car ils apparaîtront sur le certificat délivré aux élèves.", "CONSEIL FORMATEUR", "tip")

    # 6. Création de formation
    style_heading_1(doc, "6. Création d'une Formation (Cycle de Vie & Statuts)")
    style_paragraph(doc, "Une formation évolue selon 3 statuts clairement identifiés :")
    style_bullet(doc, "Invisible du grand public, en cours de rédaction par l'équipe.", "Brouillon (draft) :")
    style_bullet(doc, "En ligne, visible sur le catalogue, ouverte aux inscriptions et achats.", "Publiée (published) :")
    style_bullet(doc, "Retirée du catalogue public. Les élèves inscrits conservent leur accès mais aucune nouvelle vente n'est possible.", "Archivée (archived) :")

    # 7. Informations générales
    style_heading_1(doc, "7. Configuration des Informations Générales et Pédagogiques")
    style_paragraph(doc, "Renseignez les champs du formulaire avec soin :")
    style_bullet(doc, "Titre évocateur et valorisant pour l'Académie.", "Titre :")
    style_bullet(doc, "Niveau adapté (Débutant, Intermédiaire, Avancé, Tous niveaux).", "Niveau :")
    style_bullet(doc, "Durée estimée d'assimilation en heures (ex: 2.5).", "Durée estimée :")
    style_bullet(doc, "Saisissez un objectif par ligne (le LMS les transforme automatiquement en puces esthétiques sur le site).", "Objectifs pédagogiques :")
    style_bullet(doc, "Un prérequis par ligne pour préparer au mieux l'apprenant.", "Prérequis :")
    add_screenshot_placeholder(doc, "4", "Bloc Informations Générales et Pédagogie", "/admin/courses/course/add/", "Champs Titre, Catégorie, Formateur, Niveau, Objectifs et Prérequis.")

    # 8. Image de couverture
    style_heading_1(doc, "8. Ajout et Optimisation de l'Image de Couverture")
    style_paragraph(doc, "L'image de couverture est traitée par un utilitaire intelligent développé sur mesure (image_utils.py) :")
    style_bullet(doc, "Formats acceptés : JPEG, PNG, WebP.", "Règle 1 :")
    style_bullet(doc, "Taille brute maximale acceptée : 30 Mo (sécurité anti-DoS).", "Règle 2 :")
    style_bullet(doc, "Traitement automatique : Redimensionnement en 1920x1080 max, conversion en WebP moderne compressé (< 500 Ko) et téléversement sécurisé vers Cloudinary.", "Règle 3 :")

    # 9. Tarifs
    style_heading_1(doc, "9. Configuration des Tarifs et Modalités d'Accès")
    style_paragraph(doc, "Dans le bloc 'Tarification & Modalités d'Accès' :")
    style_bullet(doc, "Cochez 'Formation gratuite' pour offrir le cours sans paiement (le prix passe automatiquement à 0 FCFA).", "Gratuité :")
    style_bullet(doc, "Indiquez le montant net en Francs CFA (XOF) dans 'Prix actuel'.", "Tarif standard :")
    style_bullet(doc, "Renseignez un 'Prix barré' supérieur pour afficher une réduction attractive sur le catalogue.", "Prix barré :")

    # 10. Modules
    style_heading_1(doc, "10. Organisation et Structuration des Modules")
    style_paragraph(doc, "Découpez votre formation en modules thématiques progressifs directement via la section inline en bas de page du cours. Spécifiez l'ordre (0, 1, 2...) et vérifiez que la case 'Publié' est cochée.")
    add_screenshot_placeholder(doc, "5", "Gestion des modules inline", "/admin/courses/course/<id>/change/", "Sous-tableau inline des modules avec titre, ordre et statut de publication.")

    # 11 & 12. Leçons et médias
    style_heading_1(doc, "11 & 12. Création des Leçons, Vidéos et Ressources")
    style_paragraph(doc, "Chaque leçon peut proposer :")
    style_bullet(doc, "Intégration YouTube, Vimeo ou fichier MP4 direct avec lecteur HTML5 responsive 16:9.", "Vidéo :")
    style_bullet(doc, "Notes de cours riches affichées directement sous le lecteur.", "Notes textuelles :")
    style_bullet(doc, "Support PDF téléchargeable par l'apprenant dans sa session.", "Pièce jointe :")
    style_bullet(doc, "Cochez 'Aperçu gratuit' pour rendre une leçon d'introduction accessible aux visiteurs non inscrits.", "Aperçu gratuit :")

    # 13 & 14. Quiz
    style_heading_1(doc, "13 & 14. Création des Quiz et Configuration des Évaluations")
    style_paragraph(doc, "Rattachez un Quiz à une leçon de type 'Quiz d'évaluation' :")
    style_bullet(doc, "Fixez le score minimum requis (par défaut 80%).", "Seuil de réussite :")
    style_bullet(doc, "Indiquez 0 pour autoriser des essais illimités (recommandé pour une pédagogie bienveillante).", "Nombre de tentatives :")
    style_bullet(doc, "Créez vos questions (choix unique ou multiple) et cochez impérativement la case 'Est une bonne réponse' sur les options exactes.", "Options et barème :")
    style_bullet(doc, "Renseignez le champ 'Explication pédagogique' pour aider l'élève après sa tentative.", "Pédagogie :")
    add_screenshot_placeholder(doc, "6", "Formulaire d'édition de Quiz", "/admin/courses/quiz/<id>/change/", "Champs Titre, Seuil de passage, questions et tableau inline des options.")

    # 15 & 16. Inscriptions
    style_heading_1(doc, "15 & 16. Gestion des Inscriptions et Apprenants")
    style_paragraph(doc, "Dans 'Courses > Inscriptions', suivez chaque élève :")
    style_bullet(doc, "Actif (vert), Terminé (vert foncé), Expiré (rouge), Annulé (gris).", "Statuts :")
    style_bullet(doc, "Jauge en pourcentage calculée dynamiquement selon les leçons achevées.", "Progression :")
    style_bullet(doc, "Possibilité d'ajouter manuellement une inscription pour un client (bourse, SAV, paiement agence).", "Attribution manuelle :")

    # 17 & 18. Paiements CashPay
    style_heading_1(doc, "17 & 18. Gestion des Formations Payantes et CashPay")
    style_paragraph(doc, "Lorsqu'un client achète une formation via CashPay (Mobile Money Flooz ou T-Money), une commande e-commerce Order sans frais de port est créée. Dès réception de la notification de paiement, le signal Django active automatiquement l'inscription sans aucune action manuelle requise.")

    # 19 & 20. Progression et Certificats
    style_heading_1(doc, "19 & 20. Progression et Délivrance des Certificats")
    style_paragraph(doc, "Dès qu'un apprenant atteint 100% de complétion sur un cours certifiant, le système génère instantanément un certificat officiel vectoriel A4 au format PDF avec un identifiant unique (ex: VL-XXXXXXXXXXXX) et un QR code menant à la page publique de vérification.")
    add_screenshot_placeholder(doc, "7", "Administration d'un certificat officiel", "/admin/courses/certificate/<id>/change/", "Code unique, nom de l'élève, date de délivrance et statut de validité.")

    # 21 & 22. Publication et Bonnes pratiques
    style_heading_1(doc, "21 & 22. Publication, Archivage et Bonnes Pratiques")
    style_bullet(doc, "Vérifiez que toutes les leçons possèdent un contenu valide avant publication.", "Checklist :")
    style_bullet(doc, "Utilisez les actions de masse pour publier ou archiver plusieurs cours en 1 clic.", "Gain de temps :")
    style_bullet(doc, "Privilégiez des leçons courtes de 10 à 20 minutes pour maintenir l'attention.", "Rythme :")

    # 23. Exercice Pratique
    style_heading_1(doc, "23. Exercice Pratique Pas-à-Pas : Création d'un Cours Complet")
    style_paragraph(doc, "Mettez en application vos connaissances en créant la formation fictive suivante :")
    style_bullet(doc, "Bien-être & Rituels Holistiques (icône fa-feather-alt).", "Catégorie :")
    style_bullet(doc, "Initiation aux Rituels Sacrés de Protection et d'Harmonisation.", "Titre :")
    style_bullet(doc, "Débutant | Durée : 2.5h | Prix : 15 000 FCFA (Barré : 25 000 FCFA).", "Paramètres :")
    style_bullet(doc, "Module 1 (2 leçons dont 1 vidéo en aperçu gratuit), Module 2 (1 leçon pratique et 1 quiz final).", "Structure :")
    style_bullet(doc, "Quiz de 3 questions avec seuil de réussite fixé à 80%.", "Évaluation :")
    style_bullet(doc, "Passage du statut en 'Publiée' et contrôle visuel sur le catalogue public.", "Publication :")

    # 24. Erreurs courantes
    style_heading_1(doc, "24. Fiches Mémo et Résolution des Erreurs Courantes")
    table_headers = ["Symptôme constaté", "Cause probable", "Solution recommandée"]
    table_data = [
        ["Erreur téléversement image", "Fichier trop lourd ou extension non autorisée (ex: BMP, TIFF).", "Utiliser un fichier JPEG, PNG ou WebP de moins de 30 Mo."],
        ["Le cours n'apparaît pas sur le site", "Le statut est resté sur 'Brouillon'.", "Passer le statut sur 'Publiée' et enregistrer."],
        ["L'apprenant ne voit pas la vidéo", "Vidéo réglée en 'Privée' sur YouTube.", "Basculer la vidéo en 'Non répertoriée' sur YouTube."],
        ["Le quiz ne valide pas la leçon", "Score inférieur au minimum requis (ex: 80%).", "Inviter l'apprenant à réviser et retenter le quiz."],
    ]
    create_table(doc, table_headers, table_data)

    out_path = OUTPUT_DIR / "guide_administrateur_venus_luna.docx"
    doc.save(str(out_path))
    print(f"✅ Guide Administrateur DOCX généré avec succès : {out_path}")


# ==============================================================================
# 2. GÉNÉRATION DU GUIDE APPRENANT
# ==============================================================================

def generate_student_guide():
    print("⏳ Génération du Guide Apprenant DOCX...")
    doc = Document()

    # Marges et en-tête / pied de page
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

        header = section.header
        p_head = header.paragraphs[0]
        p_head.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        r_head = p_head.add_run("VENUS LUNA ACADEMY  |  GUIDE DE L'APPRENANT")
        r_head.font.size = Pt(8)
        r_head.font.color.rgb = COLOR_MUTED

        footer = section.footer
        p_foot = footer.paragraphs[0]
        p_foot.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r_foot = p_foot.add_run("Venus Luna — Guide de l'Apprenant : Découvrir et Suivre une Formation  |  v1.0.0")
        r_foot.font.size = Pt(8)
        r_foot.font.color.rgb = COLOR_MUTED

    # Page de couverture
    add_cover_page(
        doc,
        title="GUIDE DE L'APPRENANT\nDÉCOUVRIR ET SUIVRE UNE FORMATION SUR VENUS LUNA",
        subtitle="Votre Manuel d'Accompagnement Spirituel et Pédagogique",
        target_audience="Visiteurs, clients de la boutique, passionnés de bien-être, de lithothérapie et de spiritualité",
        doc_version="1.0.0",
    )

    # Sommaire
    style_heading_1(doc, "TABLE DES MATIÈRES")
    sommaire_items = [
        "1. Bienvenue à l'Académie Venus Luna",
        "2. Découvrir l'espace formation",
        "3. Parcourir et explorer le catalogue",
        "4. Rechercher et filtrer une formation",
        "5. Consulter la fiche détaillée d'une formation",
        "6. Comprendre le programme pédagogique et les prérequis",
        "7. Créer son compte apprenant",
        "8. Se connecter à son espace personnel",
        "9. S'inscrire à une formation gratuite en 1 clic",
        "10. Acheter une formation certifiante avec CashPay (Mobile Money)",
        "11. Comprendre la confirmation de commande et l'activation immédiate",
        "12. Accéder à « Mon Sanctuaire Pédagogique » (Tableau de bord)",
        "13. Naviguer dans les modules et démarrer son cours",
        "14. Consulter les leçons (Vidéos, Notes de lecture et Médias)",
        "15. Suivre son avancement et valider sa progression",
        "16. Passer les quiz d'évaluation en toute sérénité",
        "17. Consulter ses résultats et retenter un quiz",
        "18. Obtenir et télécharger son certificat officiel de réussite (PDF)",
        "19. Vérifier l'authenticité d'un certificat avec le QR Code",
        "20. Télécharger les supports de cours et documents joints",
        "21. Gérer son compte apprenant et ses informations personnelles",
        "22. Foire Aux Questions (FAQ de l'apprenant)",
        "23. Guide de dépannage et assistance technique",
    ]
    for item in sommaire_items:
        style_bullet(doc, item)

    doc.add_page_break()

    # 1. Bienvenue
    style_heading_1(doc, "1. Bienvenue à l'Académie Venus Luna")
    style_paragraph(doc, "Chère apprenante, cher apprenant, l'Académie Venus Luna vous ouvre les portes d'un enseignement spirituel et holistique exigeant mais profondément accessible. Que vous souhaitiez apprendre les secrets des pierres de lithothérapie, méditer en pleine conscience ou harmoniser votre lieu de vie, vous disposez d'un espace moderne conçu pour votre bien-être.")
    style_bullet(doc, "Accès 24h/24 et 7j/7 depuis smartphone, tablette ou ordinateur.", "Liberté totale :")
    style_bullet(doc, "Vidéos HD, notes synthétiques et ressources imprimables.", "Supports complets :")
    style_bullet(doc, "Diplôme officiel vectoriel avec QR code remis à chaque réussite.", "Certification officielle :")
    style_bullet(doc, "Paiement direct en Francs CFA via T-Money et Flooz.", "Paiement local sécurisé :")

    # 2. Découvrir
    style_heading_1(doc, "2. Découvrir l'Espace Formation")
    style_paragraph(doc, "Depuis n'importe quelle page de la boutique Venus Luna, cliquez sur l'onglet 'Formations' dans la barre de menu supérieure. Vous accédez immédiatement au catalogue complet de l'académie (/formations/).")
    add_screenshot_placeholder(doc, "1", "Bouton Formations dans la barre de navigation", "Haut de page (Navbar)", "Logo Venus Luna, liens 'Boutique', 'Blog' et bouton vert 'Formations'.")

    # 3 & 4. Parcourir et Filtrer
    style_heading_1(doc, "3 & 4. Parcourir, Rechercher et Filtrer les Formations")
    style_paragraph(doc, "Trouvez facilement la formation qui répond à vos besoins du moment :")
    style_bullet(doc, "Saisissez un mot clé (ex: 'cristaux', 'méditation') et cliquez sur 'Filtrer'.", "Recherche textuelle :")
    style_bullet(doc, "Basculez entre 'Tous', 'Gratuites' (initiations offertes) et 'Certifiantes' (cursus complets).", "Filtres tarifaires :")
    style_bullet(doc, "Cliquez sur une pilule de catégorie pour n'afficher que les cours de cette thématique.", "Catégories :")
    add_screenshot_placeholder(doc, "2", "Le catalogue et ses filtres", "/formations/", "Bannière d'accueil dorée, barre de recherche, filtres et cartes de cours.")

    # 5 & 6. Détails du cours
    style_heading_1(doc, "5 & 6. Fiche Détaillée, Objectifs et Prérequis")
    style_paragraph(doc, "En cliquant sur 'Découvrir', vous accédez à la présentation complète :")
    style_bullet(doc, "Ce que vous saurez accomplir à la fin du programme.", "Objectifs :")
    style_bullet(doc, "Les éventuels instruments nécessaires (ex: carnet, bougie, quartz).", "Prérequis :")
    style_bullet(doc, "Le découpage en modules et le repérage des leçons ouvertes en 'Aperçu gratuit'.", "Programme :")

    # 7 & 8. Compte et Connexion
    style_heading_1(doc, "7 & 8. Création de Compte et Connexion")
    style_paragraph(doc, "Pour sauvegarder votre progression et recevoir votre diplôme à votre nom :")
    style_bullet(doc, "Cliquez sur 'Mon Compte' > 'Créer un compte'.", "Inscription :")
    style_bullet(doc, "Indiquez soigneusement votre prénom et votre nom (ils apparaîtront sur votre certificat officiel).", "Nom officiel :")
    style_bullet(doc, "Connectez-vous avec vos identifiants pour débloquer votre accès.", "Connexion :")

    # 9. Inscription gratuite
    style_heading_1(doc, "9. S'inscrire à une Formation Gratuite en 1 Clic")
    style_paragraph(doc, "Pour les formations gratuites d'initiation :")
    style_bullet(doc, "Connectez-vous à votre compte Venus Luna.", "Étape 1 :")
    style_bullet(doc, "Rendez-vous sur la page de la formation gratuite.", "Étape 2 :")
    style_bullet(doc, "Cliquez sur le bouton vert 'S'inscrire gratuitement'. Vous êtes aussitôt redirigé(e) vers la première leçon !", "Étape 3 :")

    # 10 & 11. Achat CashPay
    style_heading_1(doc, "10 & 11. Acheter une Formation Certifiante avec CashPay")
    style_paragraph(doc, "Pour acquérir une formation payante certifiante :")
    style_bullet(doc, "Cliquez sur le bouton doré 'Acheter avec CashPay'.", "Étape 1 :")
    style_bullet(doc, "Sur la page sécurisée CashPay, sélectionnez T-Money ou Flooz.", "Étape 2 :")
    style_bullet(doc, "Indiquez votre numéro de téléphone et validez le paiement sur votre mobile.", "Étape 3 :")
    style_bullet(doc, "La plateforme valide la transaction automatiquement et ouvre votre accès dans la seconde.", "Confirmation :")
    add_screenshot_placeholder(doc, "3", "Bouton d'achat et passerelle CashPay", "Fiche de cours / Panneau latéral", "Montant en FCFA, bouton 'Acheter avec CashPay' et garanties incluses.")

    # 12 & 13. Mon Espace
    style_heading_1(doc, "12 & 13. Mon Sanctuaire Pédagogique (Espace Personnel)")
    style_paragraph(doc, "Accessible via 'Mes Formations' (/formations/mon-espace/) :")
    style_bullet(doc, "Visualisez vos 4 indicateurs : Formations suivies, En cours, Terminées et % moyen.", "Statistiques :")
    style_bullet(doc, "Cliquez sur le bouton vert 'Reprendre le cours' pour continuer exactement là où vous vous étiez arrêté(e).", "Reprise directe :")
    add_screenshot_placeholder(doc, "4", "Mon Sanctuaire Pédagogique", "/formations/mon-espace/", "Statistiques d'apprentissage, cartes avec jauges de progression et boutons.")

    # 14 & 15. Lecteur et Progression
    style_heading_1(doc, "14 & 15. Le Lecteur de Cours et la Validation de Leçon")
    style_paragraph(doc, "L'interface d'apprentissage est pensée pour votre sérénité :")
    style_bullet(doc, "Lecteur vidéo épuré sans publicités extérieures.", "Vidéo :")
    style_bullet(doc, "Notes rédigées par l'instructeur sous la vidéo.", "Notes de cours :")
    style_bullet(doc, "Arborescence latérale avec coches de progression.", "Programme :")
    style_bullet(doc, "Cliquez sur 'Marquer comme terminée' pour enregistrer votre succès et passer à la leçon suivante.", "Validation :")
    add_screenshot_placeholder(doc, "5", "Le lecteur de cours immersif", "/formations/<slug>/lecon/<id>/", "Vidéo 16:9, boutons 'Précédent', 'Marquer comme terminée', 'Suivant' et barre latérale.")

    # 16 & 17. Quiz
    style_heading_1(doc, "16 & 17. Passer les Quiz et Découvrir ses Résultats")
    style_paragraph(doc, "Pour les leçons comportant une évaluation :")
    style_bullet(doc, "Lisez chaque question attentivement et sélectionnez votre réponse.", "Passation :")
    style_bullet(doc, "Cliquez sur 'Valider mes réponses'. Le résultat s'affiche instantanément.", "Notation :")
    style_bullet(doc, "Dès 80% de bonnes réponses, la leçon est validée avec succès.", "Succès :")
    style_bullet(doc, "Si le score est insuffisant, lisez les explications pédagogiques fournies et retentez le quiz gratuitement !", "Bienveillance :")
    add_screenshot_placeholder(doc, "6", "Formulaire de quiz interactif", "Bas de page de leçon", "Énoncé des questions, choix multiples, score requis et bouton de soumission.")

    # 18 & 19. Certificat et QR Code
    style_heading_1(doc, "18 & 19. Obtenir son Certificat et Vérifier son Authenticité")
    style_paragraph(doc, "Dès que vous validez 100% de votre cursus certifiant :")
    style_bullet(doc, "Rendez-vous dans 'Mon Sanctuaire Pédagogique' > onglet 'Mes Certificats'.", "Accès :")
    style_bullet(doc, "Cliquez sur 'Télécharger mon certificat (PDF)' pour obtenir votre diplôme A4 haute résolution.", "Téléchargement :")
    style_bullet(doc, "Scannez le QR Code imprimé sur votre document avec un smartphone pour prouver son authenticité sur le registre officiel de Venus Luna.", "Vérification :")
    add_screenshot_placeholder(doc, "7", "Le certificat officiel et sa vérification", "Document PDF & /formations/verifier/<code>/", "Diplôme vectoriel or et émeraude avec nom, date, signature et QR code.")

    # 20 & 21. Téléchargements et Compte
    style_heading_1(doc, "20 & 21. Documents Joints et Gestion du Compte")
    style_paragraph(doc, "Téléchargez vos fiches mémos et livrets PDF dans chaque leçon via le bouton 'Télécharger le document'. Retrouvez vos factures et mettez à jour votre profil dans l'espace 'Mon Compte'.")

    # 22. FAQ
    style_heading_1(doc, "22. Foire Aux Questions (FAQ de l'Apprenant)")
    faq_data = [
        ["Ai-je une limite de temps pour finir mon cours ?", "Non. Dès votre inscription, vous disposez d'un accès illimité à vie 24h/24."],
        ["Puis-je suivre les cours sur mon smartphone ?", "Oui, la plateforme est 100% adaptée aux smartphones Android et iPhone."],
        ["Que faire si j'échoue à un quiz ?", "Vous pouvez réviser et repasser le quiz gratuitement autant de fois que nécessaire."],
        ["Quels sont les moyens de paiement acceptés ?", "Paiements sécurisés en Francs CFA par Mobile Money (T-Money, Flooz) et cartes bancaires via CashPay."],
        ["Le certificat officiel est-il payant en plus ?", "Non, la délivrance du certificat PDF haute définition est totalement incluse dans le prix de la formation."],
    ]
    create_table(doc, ["Question fréquente", "Réponse de l'Académie Venus Luna"], faq_data)

    # 23. Dépannage
    style_heading_1(doc, "23. Guide de Dépannage et Assistance")
    add_callout(doc, "Une question ou un blocage ? Contactez l'équipe d'assistance Venus Luna par e-mail à contact@venus-luna.com ou via le formulaire de contact du site. Nous vous répondrons sous 24 à 48 heures ouvrées.", "BESOIN D'AIDE ?", "tip")

    out_path = OUTPUT_DIR / "guide_apprenant_venus_luna.docx"
    doc.save(str(out_path))
    print(f"✅ Guide Apprenant DOCX généré avec succès : {out_path}")


if __name__ == "__main__":
    generate_admin_guide()
    generate_student_guide()
