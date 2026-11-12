"""
Générateur de documentation professionnelle PDF pour Venus Luna.
Produit :
1. docs/guides/guide_administrateur_venus_luna.pdf
2. docs/guides/guide_apprenant_venus_luna.pdf
Utilise ReportLab pour un rendu vectoriel haute fidélité.
"""

import os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "docs" / "guides"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Couleurs de la charte Venus Luna
COLOR_EMERAUDE = colors.HexColor("#1C683B")
COLOR_EMERAUDE_DARK = colors.HexColor("#155430")
COLOR_EMERAUDE_LIGHT = colors.HexColor("#F0F7F4")
COLOR_OR = colors.HexColor("#D4AF37")
COLOR_OR_DARK = colors.HexColor("#B8972E")
COLOR_TEXT = colors.HexColor("#2D3748")
COLOR_MUTED = colors.HexColor("#718096")
COLOR_BORDER = colors.HexColor("#CBD5E1")
COLOR_GREY_LIGHT = colors.HexColor("#F8FAFC")
COLOR_ALERT_BG = colors.HexColor("#FFFBEB")
COLOR_ALERT_BORDER = colors.HexColor("#F59E0B")


class NumberedCanvas(canvas.Canvas):
    """Canvas personnalisé permettant d'afficher 'Page X sur Y' et un en-tête professionnel."""
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
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        # Ne pas afficher sur la première page (Page de couverture)
        if self._pageNumber == 1:
            return

        self.saveState()
        width, height = A4

        # En-tête
        self.setFont("Helvetica", 8)
        self.setFillColor(COLOR_MUTED)
        self.drawRightString(width - 2 * cm, height - 1.5 * cm, "VENUS LUNA ACADEMY  |  DOCUMENTATION OFFICIELLE")
        self.setStrokeColor(COLOR_BORDER)
        self.setLineWidth(0.5)
        self.line(2 * cm, height - 1.6 * cm, width - 2 * cm, height - 1.6 * cm)

        # Pied de page
        self.line(2 * cm, 1.8 * cm, width - 2 * cm, 1.8 * cm)
        self.drawString(2 * cm, 1.3 * cm, "Institut Venus Luna  •  Guide d'Utilisation LMS  •  v1.0.0")
        self.drawRightString(width - 2 * cm, 1.3 * cm, f"Page {self._pageNumber} sur {total_pages}")

        self.restoreState()


def get_custom_styles():
    styles = getSampleStyleSheet()

    title_cover = ParagraphStyle(
        'CoverTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=28,
        textColor=COLOR_EMERAUDE,
        alignment=1,  # Centre
        spaceAfter=15,
    )

    subtitle_cover = ParagraphStyle(
        'CoverSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=COLOR_TEXT,
        alignment=1,
        spaceAfter=25,
    )

    h1 = ParagraphStyle(
        'CustomH1',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=13.5,
        leading=18,
        textColor=COLOR_EMERAUDE,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )

    h2 = ParagraphStyle(
        'CustomH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=COLOR_OR,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )

    body = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=COLOR_TEXT,
        spaceAfter=4,
    )

    bullet = ParagraphStyle(
        'CustomBullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=COLOR_TEXT,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=2,
    )

    callout_text = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=COLOR_TEXT,
    )

    return {
        'title_cover': title_cover,
        'subtitle_cover': subtitle_cover,
        'h1': h1,
        'h2': h2,
        'body': body,
        'bullet': bullet,
        'callout_text': callout_text,
    }


def make_callout(text, title="CONSEIL PRATIQUE", callout_type="tip", styles=None):
    bg = COLOR_EMERAUDE_LIGHT if callout_type == "tip" else COLOR_ALERT_BG
    border = COLOR_EMERAUDE if callout_type == "tip" else COLOR_ALERT_BORDER
    icon = "💡 " if callout_type == "tip" else "⚠️ "
    color_title = "#1C683B" if callout_type == "tip" else "#B45309"

    p_content = Paragraph(
        f"<b>{icon}<font color='{color_title}'>{title}</font></b><br/>{text}",
        styles['callout_text']
    )

    t = Table([[p_content]], colWidths=[17 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('LINELEFT', (0, 0), (-1, -1), 3.5, border),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    return t


def make_screenshot_placeholder(number, title, path_desc, elements_desc, styles=None):
    html = f"""
    <b><font color='#D4AF37'>📸 EMPLACEMENT VISUEL RÉEL — CAPTURE D'ÉCRAN N°{number}</font></b><br/>
    <b><font size='10' color='#1C683B'>{title}</font></b><br/>
    <i><font color='#718096' size='8'>📍 Emplacement dans l'application : {path_desc}</font></i><br/>
    <font size='8.5'>🔍 Éléments clés identifiés : {elements_desc}</font><br/>
    <font color='#A0AEC0' size='7.5'>ℹ️ Note : Emplacement réservé pour insertion de capture sans données confidentielles.</font>
    """
    p = Paragraph(html, styles['callout_text'])
    t = Table([[p]], colWidths=[17 * cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COLOR_GREY_LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('LINELEFT', (0, 0), (-1, -1), 3.0, COLOR_OR),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    return t


def make_table(headers, data, col_widths=None, styles=None):
    t_data = []
    # En-têtes
    hdr_row = [Paragraph(f"<b><font color='white'>{h}</font></b>", styles['callout_text']) for h in headers]
    t_data.append(hdr_row)

    # Données
    for r_idx, row in enumerate(data):
        row_cells = [Paragraph(cell, styles['callout_text']) for cell in row]
        t_data.append(row_cells)

    if not col_widths:
        col_widths = [17 * cm / len(headers)] * len(headers)

    t = Table(t_data, colWidths=col_widths)
    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_EMERAUDE),
        ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]
    for i in range(1, len(t_data)):
        bg = COLOR_GREY_LIGHT if i % 2 == 0 else colors.white
        t_style.append(('BACKGROUND', (0, i), (-1, i), bg))

    t.setStyle(TableStyle(t_style))
    return t


# ==============================================================================
# 1. GÉNÉRATEUR DU GUIDE ADMINISTRATEUR PDF
# ==============================================================================

def generate_admin_pdf():
    print("⏳ Génération du Guide Administrateur PDF...")
    out_file = OUTPUT_DIR / "guide_administrateur_venus_luna.pdf"
    doc = SimpleDocTemplate(
        str(out_file),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2.2 * cm,
        bottomMargin=2.2 * cm,
    )
    styles = get_custom_styles()
    story = []

    # 1. Page de Couverture
    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph("<b><font color='#D4AF37' size='13'>INSTITUT SPIRITUEL & BIEN-ÊTRE VENUS LUNA</font></b>", styles['subtitle_cover']))
    story.append(Paragraph("❖  •  ━━━━━━━━━━━━━━━━━━━━━━━  •  ❖", styles['subtitle_cover']))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph("GUIDE D'ADMINISTRATION ET DE GESTION DES FORMATIONS", styles['title_cover']))
    story.append(Paragraph("Manuel Complet d'Exploitation et d'Ingénierie Pédagogique", styles['subtitle_cover']))
    story.append(Spacer(1, 1 * cm))

    meta_table_data = [
        [Paragraph("<b>Public Cible :</b>", styles['callout_text']), Paragraph("Administrateurs, gestionnaires e-commerce et formateurs habilités", styles['callout_text'])],
        [Paragraph("<b>Version :</b>", styles['callout_text']), Paragraph("Version 1.0.0 (Production)", styles['callout_text'])],
        [Paragraph("<b>Date d'Édition :</b>", styles['callout_text']), Paragraph("Novembre 2026", styles['callout_text'])],
        [Paragraph("<b>Plateforme :</b>", styles['callout_text']), Paragraph("Venus Luna Django E-Commerce & LMS", styles['callout_text'])],
    ]
    meta_table = Table(meta_table_data, colWidths=[4.5 * cm, 11 * cm])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), COLOR_EMERAUDE_LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)

    story.append(Spacer(1, 3.5 * cm))
    story.append(Paragraph("<font color='#718096' size='8'>Documentation Officielle d'Exploitation — Lomé, Togo</font>", styles['subtitle_cover']))
    story.append(PageBreak())

    # 2. Sommaire
    story.append(Paragraph("TABLE DES MATIÈRES", styles['h1']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_OR, spaceAfter=10))
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
        story.append(Paragraph(f"• {item}", styles['bullet']))
    story.append(PageBreak())

    # Contenu détaillé
    story.append(Paragraph("1. Présentation Générale du LMS Venus Luna", styles['h1']))
    story.append(Paragraph("Le module LMS (Learning Management System) de Venus Luna est une extension native intégrée à la plateforme e-commerce Django. Il permet à l'Académie Venus Luna de proposer une offre d'apprentissage spirituel complète (lithothérapie, méditation, chakras, rituels sacrés) avec un suivi automatisé des inscriptions, de la progression et de la certification.", styles['body']))
    story.append(Paragraph("• <b>CourseCategory :</b> Catégorisation thématique avec icônes FontAwesome et ordre d'affichage.", styles['bullet']))
    story.append(Paragraph("• <b>Course :</b> Programme pédagogique (titre, niveau, tarifs FCFA, objectifs, certification).", styles['bullet']))
    story.append(Paragraph("• <b>CourseModule :</b> Chapitre thématique regroupant une séquence logique de leçons.", styles['bullet']))
    story.append(Paragraph("• <b>Lesson :</b> Unité multimédia (vidéos YouTube/Vimeo/MP4, supports PDF, notes de cours ou quiz).", styles['bullet']))
    story.append(Paragraph("• <b>Enrollment :</b> Traçabilité des accès apprenants, complétion et dernière leçon consultée.", styles['bullet']))
    story.append(Paragraph("• <b>Certificate :</b> Diplôme officiel vectoriel A4 paysage avec code unique VL-... et QR code.", styles['bullet']))

    story.append(Paragraph("2. Connexion à l'Espace d'Administration", styles['h1']))
    story.append(Paragraph("L'accès s'effectue via l'URL <code>https://venus-luna.com/admin/</code> (ou <code>http://127.0.0.1:8000/admin/</code> en local) avec un compte disposant de la permission 'Statut équipe' (is_staff=True).", styles['body']))
    story.append(make_screenshot_placeholder("1", "Écran de connexion à l'administration", "/admin/login/", "Champs Nom d'utilisateur, Mot de passe et bouton de validation.", styles=styles))
    story.append(make_callout("Ne mémorisez jamais vos identifiants sur un poste partagé et déconnectez-vous en fin de session.", "SÉCURITÉ DES ACCÈS", "warning", styles=styles))

    story.append(Paragraph("3. Présentation du Tableau de Bord d'Administration", styles['h1']))
    story.append(Paragraph("Dans la console d'accueil Django, descendez jusqu'au bloc <b>COURSES</b>. Il regroupe l'accès direct aux catégories, cours, leçons, inscriptions, quiz et certificats.", styles['body']))
    story.append(make_screenshot_placeholder("2", "Tableau de bord - Section COURSES", "/admin/", "Liste des tables avec compteurs et boutons d'ajout '+ Ajouter'.", styles=styles))

    story.append(Paragraph("4. Gestion des Catégories de Formation", styles['h1']))
    story.append(Paragraph("Chemin : <code>Courses > Catégories de formation > + Ajouter</code>. Renseignez le Nom (ex: 'Lithothérapie & Cristaux'), l'icône FontAwesome (ex: 'fa-gem', 'fa-spa', 'fa-moon') et l'ordre d'affichage.", styles['body']))
    story.append(make_screenshot_placeholder("3", "Formulaire d'ajout d'une catégorie", "/admin/courses/coursecategory/add/", "Champs Nom, Slug, Description, Icône et Ordre.", styles=styles))

    story.append(Paragraph("5. Gestion des Formateurs et Comptes Instructeurs", styles['h1']))
    story.append(Paragraph("Créez ou modifiez le compte du formateur dans 'Utilisateurs' : cochez 'Statut équipe' et attribuez-lui le groupe 'Formateurs'. Grâce au cloisonnement de sécurité du LMS, il ne verra dans l'administration que ses propres cours.", styles['body']))
    story.append(make_callout("Renseignez toujours le prénom et le nom de l'instructeur car ils figureront sur les certificats délivrés aux élèves.", "CONSEIL FORMATEUR", "tip", styles=styles))

    story.append(Paragraph("6. Création d'une Formation (Cycle de Vie & Statuts)", styles['h1']))
    story.append(Paragraph("Une formation évolue selon 3 statuts :", styles['body']))
    story.append(Paragraph("• <b>Brouillon (draft) :</b> Invisible du public, en cours de rédaction par l'équipe.", styles['bullet']))
    story.append(Paragraph("• <b>Publiée (published) :</b> En ligne, visible sur le catalogue, ouverte aux inscriptions.", styles['bullet']))
    story.append(Paragraph("• <b>Archivée (archived) :</b> Retirée du catalogue, accès conservé pour les inscrits existants.", styles['bullet']))

    story.append(Paragraph("7. Configuration des Informations Générales et Pédagogiques", styles['h1']))
    story.append(Paragraph("Renseignez le Titre, le Niveau (Débutant, Intermédiaire, Avancé, Tous niveaux), la Durée estimée en heures. Renseignez un objectif par ligne dans 'Objectifs pédagogiques' : le LMS les formate automatiquement en puces graphiques sur la fiche publique.", styles['body']))
    story.append(make_screenshot_placeholder("4", "Bloc Informations Générales et Pédagogie", "/admin/courses/course/add/", "Champs Titre, Niveau, Durée, Objectifs et Prérequis.", styles=styles))

    story.append(Paragraph("8. Ajout et Optimisation de l'Image de Couverture", styles['h1']))
    story.append(Paragraph("Formats acceptés : JPEG, PNG, WebP (max 30 Mo). Le moteur optimise automatiquement l'image : redimensionnement 1920x1080 max, compression WebP (< 500 Ko) et téléversement sécurisé vers Cloudinary.", styles['body']))

    story.append(Paragraph("9. Configuration des Tarifs et Modalités d'Accès", styles['h1']))
    story.append(Paragraph("Cochez 'Formation gratuite' pour offrir le cours sans paiement (0 FCFA). Pour une formation payante, renseignez le 'Prix actuel' en FCFA et éventuellement un 'Prix barré' pour afficher une promotion.", styles['body']))

    story.append(Paragraph("10. Organisation et Structuration des Modules", styles['h1']))
    story.append(Paragraph("Découpez le cours en modules via la section inline en bas de page du cours : renseignez le Titre, l'Ordre (0, 1, 2...) et vérifiez que 'Publié' est coché.", styles['body']))
    story.append(make_screenshot_placeholder("5", "Gestion des modules inline", "/admin/courses/course/<id>/change/", "Sous-tableau des modules avec Titre, Ordre et coche Publié.", styles=styles))

    story.append(Paragraph("11 & 12. Création des Leçons, Vidéos et Ressources", styles['h1']))
    story.append(Paragraph("Chaque leçon prend en charge : des vidéos YouTube/Vimeo ou fichiers MP4 directs en 16:9, des notes textuelles riches, et des pièces jointes PDF téléchargeables par l'apprenant. Cochez 'Aperçu gratuit' pour ouvrir une leçon d'initiation aux visiteurs non inscrits.", styles['body']))

    story.append(Paragraph("13 & 14. Création des Quiz et Configuration des Évaluations", styles['h1']))
    story.append(Paragraph("Rattachez un Quiz à une leçon : définissez le score minimum (ex: 80%) et le nombre d'essais (0 = illimité). Ajoutez les questions et cochez impérativement la case 'Est une bonne réponse' sur les options exactes. Renseignez l'explication pédagogique affichée à l'élève après son test.", styles['body']))
    story.append(make_screenshot_placeholder("6", "Édition de Quiz et Questions", "/admin/courses/quiz/<id>/change/", "Score requis, questions et options avec coche 'Est une bonne réponse'.", styles=styles))

    story.append(Paragraph("15 & 16. Gestion des Inscriptions et Apprenants", styles['h1']))
    story.append(Paragraph("Dans 'Courses > Inscriptions', suivez les apprenants avec jauge de progression en temps réel (ex: 75%). Vous pouvez attribuer manuellement une inscription en 1 clic pour un client (bourse, SAV).", styles['body']))

    story.append(Paragraph("17 & 18. Gestion des Paiements CashPay", styles['h1']))
    story.append(Paragraph("L'achat d'une formation par Mobile Money (Flooz ou T-Money) via CashPay crée une commande e-commerce. Dès validation du paiement, le signal Django active automatiquement l'accès au cours.", styles['body']))

    story.append(Paragraph("19 & 20. Progression et Délivrance des Certificats", styles['h1']))
    story.append(Paragraph("Dès que 100% des leçons d'un cours certifiant sont complétées, le certificat vectoriel A4 paysage ReportLab est automatiquement généré avec un code unique VL-XXXXXXXXXXXX et un QR code officiel de contrôle.", styles['body']))
    story.append(make_screenshot_placeholder("7", "Administration d'un certificat officiel", "/admin/courses/certificate/<id>/change/", "Code VL-..., titulaire, cours, date et case 'Certificat valide'.", styles=styles))

    story.append(Paragraph("21 & 22. Publication et Bonnes Pratiques", styles['h1']))
    story.append(Paragraph("Vérifiez l'ensemble des leçons avant de basculer en 'Publiée'. Privilégiez des vidéos de 10 à 20 minutes pour optimiser le taux de complétion.", styles['body']))

    story.append(Paragraph("23. Exercice Pratique Pas-à-Pas : Création d'un Cours", styles['h1']))
    story.append(Paragraph("Entraînez-vous en créant la formation 'Initiation aux Rituels Sacrés de Protection' : Catégorie Bien-être & Rituels (fa-feather-alt), Niveau Débutant, Durée 2.5h, Prix 15 000 FCFA, 2 modules avec 4 leçons, 1 quiz final noté à 80% et publication sur le catalogue.", styles['body']))

    story.append(Paragraph("24. Résolution des Erreurs Courantes", styles['h1']))
    table_headers = ["Symptôme", "Cause probable", "Solution recommandée"]
    table_data = [
        ["Erreur image couverture", "Format non supporté ou fichier trop lourd.", "Utiliser un fichier JPEG, PNG ou WebP < 30 Mo."],
        ["Cours invisible sur le site", "Statut resté sur 'Brouillon'.", "Passer le statut sur 'Publiée'."],
        ["Vidéo inaccessible à l'élève", "Vidéo réglée en 'Privée' sur YouTube.", "Régler la visibilité sur 'Non répertoriée'."],
        ["Quiz ne validant pas la leçon", "Score inférieur au seuil requis (ex: 80%).", "Inviter l'apprenant à réviser et retenter le quiz."],
    ]
    story.append(make_table(table_headers, table_data, col_widths=[4.5 * cm, 5.5 * cm, 7.0 * cm], styles=styles))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"✅ Guide Administrateur PDF généré avec succès : {out_file}")


# ==============================================================================
# 2. GÉNÉRATEUR DU GUIDE APPRENANT PDF
# ==============================================================================

def generate_student_pdf():
    print("⏳ Génération du Guide Apprenant PDF...")
    out_file = OUTPUT_DIR / "guide_apprenant_venus_luna.pdf"
    doc = SimpleDocTemplate(
        str(out_file),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2.2 * cm,
        bottomMargin=2.2 * cm,
    )
    styles = get_custom_styles()
    story = []

    # 1. Page de Couverture
    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph("<b><font color='#D4AF37' size='13'>ACADÉMIE & SANCTUAIRE PÉDAGOGIQUE VENUS LUNA</font></b>", styles['subtitle_cover']))
    story.append(Paragraph("❖  •  ━━━━━━━━━━━━━━━━━━━━━━━  •  ❖", styles['subtitle_cover']))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph("GUIDE DE L'APPRENANT\nDÉCOUVRIR ET SUIVRE UNE FORMATION", styles['title_cover']))
    story.append(Paragraph("Votre Manuel d'Accompagnement Spirituel et Pédagogique", styles['subtitle_cover']))
    story.append(Spacer(1, 1 * cm))

    meta_table_data = [
        [Paragraph("<b>Public Cible :</b>", styles['callout_text']), Paragraph("Visiteurs, clients de la boutique et apprenants de l'Académie", styles['callout_text'])],
        [Paragraph("<b>Version :</b>", styles['callout_text']), Paragraph("Version 1.0.0 (Grand Public)", styles['callout_text'])],
        [Paragraph("<b>Date d'Édition :</b>", styles['callout_text']), Paragraph("Novembre 2026", styles['callout_text'])],
        [Paragraph("<b>Plateforme :</b>", styles['callout_text']), Paragraph("Venus Luna Django E-Commerce & LMS", styles['callout_text'])],
    ]
    meta_table = Table(meta_table_data, colWidths=[4.5 * cm, 11 * cm])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), COLOR_EMERAUDE_LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)

    story.append(Spacer(1, 3.5 * cm))
    story.append(Paragraph("<font color='#718096' size='8'>Guide Pédagogique Officiel — Vénus-Luna Lomé (Togo)</font>", styles['subtitle_cover']))
    story.append(PageBreak())

    # 2. Sommaire
    story.append(Paragraph("TABLE DES MATIÈRES", styles['h1']))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_OR, spaceAfter=10))
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
        story.append(Paragraph(f"• {item}", styles['bullet']))
    story.append(PageBreak())

    # Contenu détaillé
    story.append(Paragraph("1. Bienvenue à l'Académie Venus Luna", styles['h1']))
    story.append(Paragraph("Chère apprenante, cher apprenant, bienvenue à l'Académie Venus Luna ! Notre plateforme vous permet de développer vos connaissances en lithothérapie, méditation et rituels sacrés en toute sérénité.", styles['body']))
    story.append(Paragraph("• <b>À votre rythme :</b> Accès illimité 24h/24 sur mobile, tablette et ordinateur.", styles['bullet']))
    story.append(Paragraph("• <b>Pédagogie bienveillante :</b> Vidéos claires, notes de synthèse et documents PDF.", styles['bullet']))
    story.append(Paragraph("• <b>Certificat officiel :</b> Diplôme infalsifiable avec QR code remis dès la fin de chaque formation certifiante.", styles['bullet']))
    story.append(Paragraph("• <b>Paiement sécurisé :</b> Règlement direct par Mobile Money (T-Money, Flooz) via CashPay.", styles['bullet']))

    story.append(Paragraph("2. Découvrir l'Espace Formation", styles['h1']))
    story.append(Paragraph("Depuis le menu haut du site, cliquez sur l'onglet <b>Formations</b> pour accéder au grand catalogue de l'Académie (/formations/).", styles['body']))
    story.append(make_screenshot_placeholder("1", "Lien Formations dans la barre de navigation", "Haut de page (Navbar)", "Logo, liens Boutique, Blog et bouton 'Formations'.", styles=styles))

    story.append(Paragraph("3 & 4. Parcourir, Rechercher et Filtrer", styles['h1']))
    story.append(Paragraph("Utilisez la barre de recherche (ex: 'cristaux') et filtrez par tarif (Toutes, Gratuites, Certifiantes) ou par thématique en cliquant sur les pilules de catégories.", styles['body']))
    story.append(make_screenshot_placeholder("2", "Le catalogue et ses filtres", "/formations/", "Bannière dorée, barre de recherche, filtres et cartes de cours.", styles=styles))

    story.append(Paragraph("5 & 6. Fiche Détaillée, Objectifs et Prérequis", styles['h1']))
    story.append(Paragraph("En cliquant sur 'Découvrir', consultez les objectifs de formation, les prérequis éventuels et le programme modulaire. Certaines leçons marquées 'Aperçu gratuit' peuvent être visionnées librement.", styles['body']))

    story.append(Paragraph("7 & 8. Création de Compte et Connexion", styles['h1']))
    story.append(Paragraph("Créez votre compte dans 'Mon Compte' > 'Créer un compte'. Renseignez soigneusement votre prénom et votre nom : ce sont ces informations exactes qui figureront sur votre certificat officiel.", styles['body']))

    story.append(Paragraph("9. S'inscrire à une Formation Gratuite en 1 Clic", styles['h1']))
    story.append(Paragraph("Sur une formation gratuite, cliquez simplement sur le bouton vert <b>'S'inscrire gratuitement'</b>. Vous accédez immédiatement à la première leçon sans aucun paiement !", styles['body']))

    story.append(Paragraph("10 & 11. Acheter avec CashPay (Mobile Money)", styles['h1']))
    story.append(Paragraph("Sur une formation certifiante, cliquez sur <b>'Acheter avec CashPay'</b>. Choisissez T-Money ou Flooz, confirmez sur votre mobile, et votre accès est débloqué dans la seconde !", styles['body']))
    story.append(make_screenshot_placeholder("3", "Bouton d'achat et passerelle CashPay", "Panneau latéral de cours", "Tarif en FCFA, bouton 'Acheter avec CashPay' et garanties.", styles=styles))

    story.append(Paragraph("12 & 13. Mon Sanctuaire Pédagogique (Espace Personnel)", styles['h1']))
    story.append(Paragraph("Dans 'Mes Formations' (/formations/mon-espace/), retrouvez vos 4 indicateurs et cliquez sur <b>'Reprendre le cours'</b> pour retrouver immédiatement votre dernière leçon vue.", styles['body']))
    story.append(make_screenshot_placeholder("4", "Mon Sanctuaire Pédagogique", "/formations/mon-espace/", "Statistiques d'apprentissage, jauges de progression et boutons.", styles=styles))

    story.append(Paragraph("14 & 15. Le Lecteur de Cours et la Progression", styles['h1']))
    story.append(Paragraph("Visionnez la vidéo, parcourez les notes sous le lecteur, puis cliquez sur <b>'Marquer comme terminée'</b> pour enregistrer votre avancement et passer à la leçon suivante.", styles['body']))
    story.append(make_screenshot_placeholder("5", "Le lecteur de cours immersif", "/formations/<slug>/lecon/<id>/", "Vidéo 16:9, boutons de navigation et barre latérale des modules.", styles=styles))

    story.append(Paragraph("16 & 17. Passer les Quiz et Découvrir ses Résultats", styles['h1']))
    story.append(Paragraph("Répondez aux questions d'évaluation et cliquez sur 'Valider mes réponses'. Dès 80% de réussite, la leçon est validée. En cas de score inférieur, lisez les explications pédagogiques fournies et retentez le quiz gratuitement !", styles['body']))
    story.append(make_screenshot_placeholder("6", "Formulaire de quiz d'évaluation", "Bas de page de leçon", "Questions, options à cocher, score requis et validation.", styles=styles))

    story.append(Paragraph("18 & 19. Obtenir son Certificat et Vérifier son Authenticité", styles['h1']))
    story.append(Paragraph("Dès 100% de complétion sur un cours certifiant, téléchargez votre certificat officiel vectoriel A4 en PDF dans 'Mes Certificats'. Scannez le QR code pour prouver son authenticité sur le registre officiel de Venus Luna.", styles['body']))
    story.append(make_screenshot_placeholder("7", "Le certificat officiel et sa vérification", "Document PDF & /formations/verifier/<code>/", "Diplôme vectoriel avec nom, date, signature et QR code.", styles=styles))

    story.append(Paragraph("20 & 21. Téléchargements et Gestion du Compte", styles['h1']))
    story.append(Paragraph("Téléchargez vos fiches mémos et supports de cours via le bouton 'Télécharger le document'. Modifiez vos informations personnelles et retrouvez vos reçus dans 'Mon Compte'.", styles['body']))

    story.append(Paragraph("22. Foire Aux Questions (FAQ de l'Apprenant)", styles['h1']))
    faq_data = [
        ["Ai-je une limite de temps ?", "Non, vous bénéficiez d'un accès à vie 24h/24."],
        ["Puis-je suivre sur smartphone ?", "Oui, le site est 100% compatible iPhone et Android."],
        ["Que faire si j'échoue à un quiz ?", "Vous pouvez réviser et repasser le quiz gratuitement."],
        ["Quels sont les paiements acceptés ?", "Paiements sécurisés en FCFA par Mobile Money (T-Money, Flooz)."],
        ["Le certificat est-il payant en plus ?", "Non, la délivrance du certificat PDF est 100% incluse."],
    ]
    story.append(make_table(["Question fréquente", "Réponse de l'Académie Venus Luna"], faq_data, col_widths=[5.5 * cm, 11.5 * cm], styles=styles))

    story.append(Paragraph("23. Assistance et Dépannage", styles['h1']))
    story.append(make_callout("Une question ou une difficulté ? Notre équipe vous répond sous 24 à 48h ouvrées par e-mail à contact@venus-luna.com ou via le formulaire de contact du site.", "BESOIN D'AIDE ?", "tip", styles=styles))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"✅ Guide Apprenant PDF généré avec succès : {out_file}")


if __name__ == "__main__":
    generate_admin_pdf()
    generate_student_pdf()

