# GUIDE D'ADMINISTRATION ET DE GESTION DES FORMATIONS
# VENUS LUNA

**Académie & Institut de Formation en Ligne Venus Luna**  
**Version du document :** 1.0.0  
**Date d'édition :** Novembre 2026  
**Public cible :** Administrateurs de la plateforme, gestionnaires pédagogiques, coordinateurs e-commerce et formateurs référents habilités.

---

## SOMMAIRE GÉNÉRAL

1. **Présentation générale du LMS Venus Luna**
2. **Connexion à l'espace d'administration**
3. **Présentation du tableau de bord d'administration**
4. **Gestion des catégories de formation**
5. **Gestion des formateurs et des comptes instructeurs**
6. **Création d'une formation (Cycle de vie & Statuts)**
7. **Configuration des informations générales et pédagogiques**
8. **Ajout et optimisation de l'image de couverture**
9. **Configuration des tarifs et modalités d'accès**
10. **Organisation et structuration des modules**
11. **Création et paramétrage des leçons**
12. **Ajout de vidéos et ressources pédagogiques jointes**
13. **Création des quiz d'évaluation**
14. **Configuration des questions, options et barèmes**
15. **Gestion administrative des inscriptions (Enrollments)**
16. **Gestion des apprenants et profils utilisateurs**
17. **Gestion des formations gratuites**
18. **Gestion des formations payantes et commandes CashPay**
19. **Suivi de progression des apprenants**
20. **Configuration, délivrance et vérification des certificats**
21. **Publication, modification et archivage des cours**
22. **Bonnes pratiques de gestion et recommandations éditoriales**
23. **Exercice pratique pas-à-pas : Création intégrale d'une formation certifiante**
24. **Fiches mémo et guide de résolution des erreurs courantes**

---

## 1. PRÉSENTATION GÉNÉRALE DU LMS VENUS LUNA

Le module **LMS (Learning Management System)** de Venus Luna est une extension native et sur-mesure de la plateforme e-commerce Django. Il permet à l'Académie Venus Luna de proposer à son public une offre complète d'apprentissage spirituel, ésotérique et holistique (lithothérapie, méditation de pleine conscience, énergétique, rituels sacrés).

### 1.1 Architecture fonctionnelle du LMS
Le LMS s'articule autour de 6 concepts clés :
- **Catégorie (`CourseCategory`)** : Classement thématique doté d'une icône FontAwesome, d'un ordre d'apparition et d'une description.
- **Formation (`Course`)** : Programme pédagogique global caractérisé par son niveau, son tarif, son formateur référent, ses objectifs, ses prérequis et sa délivrance de certificat.
- **Module (`CourseModule`)** : Chapitre thématique regroupant une suite logique de leçons.
- **Leçon (`Lesson`)** : Unité d'apprentissage multimédia (vidéo interactive, document PDF téléchargeable, article textuel de référence ou quiz d'évaluation).
- **Inscription (`Enrollment`)** : Droit d'accès accordé à un utilisateur pour un cours donné, traçant sa date d'entrée, sa source d'acquisition (gratuite, achat CashPay ou ajout manuel) et son état d'avancement.
- **Certification (`Certificate`)** : Diplôme numérique officiel infalsifiable muni d'un code unique `VL-XXXXXXXXXXXX`, vérifiable en ligne et téléchargeable au format PDF haute fidélité.

### 1.2 Rôles et niveaux de privilèges
L'écosystème Venus Luna distingue 4 niveaux d'acteurs :
1. **Superadministrateur (`is_superuser=True`)** : Accès sans restriction à l'ensemble du système, configuration globale, modification de tous les cours, annulation/validation de toutes les inscriptions et gestion des comptes.
2. **Gestionnaire / Staff (`is_staff=True`)** : Supervision administrative, création et modération des cours, assistance apprenants, consultation des commandes et statistiques.
3. **Formateur Référent (Groupe `Formateurs`)** : Enseignant habilité dont le compte est rattaché au groupe spécifique. Dans l'administration Django, le formateur a un accès ciblé restreint : il ne consulte, ne modifie et ne gère que les formations dont il est désigné comme l'instructeur principal.
4. **Apprenant / Client** : Accès public au catalogue et consultation privée de son espace de formation (`/formations/mon-espace/`).

---

## 2. CONNEXION À L'ESPACE D'ADMINISTRATION

L'accès à l'interface de gestion requiert une authentification stricte avec un compte membre du personnel (`is_staff=True`).

### Procédure de connexion :
1. Ouvrez votre navigateur web moderne (Google Chrome, Mozilla Firefox, Microsoft Edge, Safari).
2. Saisissez l'adresse de l'interface d'administration :  
   `https://venus-luna.com/admin/` (ou en local : `http://127.0.0.1:8000/admin/`).
3. Saisissez votre **Nom d'utilisateur** et votre **Mot de passe**.
4. Cliquez sur le bouton **Se connecter**.

```
+-----------------------------------------------------------------------+
|  [CAPTURE D'ÉCRAN N°1 : ÉCRAN DE CONNEXION DJANGO ADMIN]              |
|  Emplacement : Page /admin/login/                                     |
|  Éléments visibles : Logo Venus Luna, champs "Nom d'utilisateur" et   |
|  "Mot de passe", bouton "Se connecter" émeraude.                      |
+-----------------------------------------------------------------------+
```

> **Conseil de sécurité :**  
> Ne cochez jamais l'option d'enregistrement automatique du mot de passe sur un ordinateur partagé. Déconnectez-vous systématiquement à la fin de votre session de gestion via le lien **Déconnexion** situé en haut à droite.

---

## 3. PRÉSENTATION DU TABLEAU DE BORD D'ADMINISTRATION

Dès votre connexion réussie, vous arrivez sur la page d'accueil de l'administration Django.

### 3.1 Emplacement de la section Formations
Faites défiler la liste des modules jusqu'à la section intitulée **COURSES** (ou **FORMATIONS**). Cette section regroupe l'intégralité des 8 tables du LMS :
- **Catégories de formation** (`CourseCategory`)
- **Formations** (`Course`)
- **Modules de formation** (`CourseModule`)
- **Leçons** (`Lesson`)
- **Inscriptions** (`Enrollment`)
- **Progressions de leçons** (`LessonProgress`)
- **Quiz** et **Questions de quiz** (`Quiz`, `QuizQuestion`)
- **Tentatives de quiz** (`QuizAttempt`)
- **Certificats** (`Certificate`)

```
+-----------------------------------------------------------------------+
|  [CAPTURE D'ÉCRAN N°2 : ACCUEIL DE L'ADMINISTRATION - SECTION COURSES]|
|  Emplacement : Page d'accueil /admin/                                 |
|  Éléments visibles : Bloc COURSES avec ses tables et boutons          |
|  d'ajout rapide "+ Ajouter".                                          |
+-----------------------------------------------------------------------+
```

---

## 4. GESTION DES CATÉGORIES DE FORMATION

Les catégories permettent de segmenter l'offre pédagogique sur le catalogue public (ex: *Lithothérapie*, *Méditation*, *Énergétique*).

- **Objectif :** Créer ou organiser les axes thématiques de l'académie.
- **Chemin d'accès :** `Accueil Admin > Courses > Catégories de formation`.

### Étapes de création d'une catégorie :
1. Cliquez sur le bouton **+ Ajouter Catégorie de formation** en haut à droite.
2. Renseignez les champs suivants :
   - **Nom de la catégorie** (ex: `Lithothérapie & Cristaux`) : Intitulé clair et engageant.
   - **Slug** : Laissez vide lors de la création ; il se génère automatiquement à partir du nom.
   - **Description** : Court paragraphe expliquant l'essence de la thématique aux apprenants.
   - **Icône FontAwesome** (ex: `fa-gem`, `fa-spa`, `fa-moon`, `fa-leaf`) : Classe CSS de l'icône affichée sur les boutons filtres du catalogue.
   - **Ordre d'affichage** : Nombre entier (1, 2, 3...) définissant la priorité d'affichage sur le site.
3. Cliquez sur **Enregistrer**.

```
+-----------------------------------------------------------------------+
|  [CAPTURE D'ÉCRAN N°3 : FORMULAIRE D'AJOUT D'UNE CATÉGORIE]           |
|  Emplacement : /admin/courses/coursecategory/add/                     |
|  Éléments visibles : Champs Nom, Slug, Description, Icône FontAwesome |
|  et bouton "Enregistrer".                                             |
+-----------------------------------------------------------------------+
```

---

## 5. GESTION DES FORMATEURS ET COMPTES INSTRUCTEURS

Chaque formation peut être attribuée à un formateur spécifique, mettant en valeur son expertise auprès des apprenants et sur le certificat final.

- **Objectif :** Créer un profil de formateur et lui attribuer les droits nécessaires.
- **Chemin d'accès :** `Accueil Admin > Authentification et autorisations > Utilisateurs`.

### Étapes pour nommer un formateur :
1. Rendez-vous sur la liste des **Utilisateurs** et cliquez sur le profil du formateur (ou créez-en un nouveau avec **+ Ajouter Utilisateur**).
2. Dans la section **Informations personnelles**, veillez à renseigner son **Prénom**, son **Nom** et son **Adresse e-mail** (ces éléments apparaîtront sur les pages de cours et certificats).
3. Dans la section **Permissions** :
   - Cochez **Statut équipe (is_staff)** pour lui donner l'accès à l'interface `/admin/`.
   - Dans le sélecteur de groupes, ajoutez-le au groupe **Formateurs**.
4. Cliquez sur **Enregistrer**.

> **Note importante sur la confidentialité formateur :**  
> Grâce au filtrage automatique programmé dans le LMS, un formateur rattaché au groupe *Formateurs* ne verra dans l'administration que ses propres cours. Il ne peut ni altérer ni consulter les formations d'autres instructeurs.

---

## 6. CRÉATION D'UNE FORMATION (CYCLE DE VIE & STATUTS)

Une formation traverse 3 statuts fondamentaux au cours de son existence :
- **Brouillon (`draft`)** : En cours de rédaction par le formateur. Invisible du grand public sur le catalogue.
- **Publiée (`published`)** : En ligne, visible sur le catalogue, accessible aux inscriptions et aux achats.
- **Archivée (`archived`)** : Retirée du catalogue public. Les apprenants déjà inscrits conservent leur accès historique, mais aucune nouvelle inscription n'est acceptée.

- **Objectif :** Initialiser la structure globale d'une formation.
- **Chemin d'accès :** `Accueil Admin > Courses > Formations > + Ajouter Formation`.

---

## 7. CONFIGURATION DES INFORMATIONS GÉNÉRALES ET PÉDAGOGIQUES

Le formulaire de création d'une formation est structuré en plusieurs blocs logiques (`fieldsets`) :

### 7.1 Bloc « Présentation de la Formation »
- **Titre** : Titre complet et évocateur (ex: *Maîtrise des 7 Cristaux et Chakras*).
- **Slug** : Laissez vide, Django génère un permalien optimisé pour le référencement naturel (SEO).
- **Catégorie** : Sélectionnez la thématique rattachée.
- **Formateur** : Sélectionnez l'instructeur référent dans la liste déroulante.
- **Niveau** : Choisissez parmi *Débutant*, *Intermédiaire*, *Avancé* ou *Tous niveaux*.
- **Durée estimée (heures)** : Durée approximative requise par l'apprenant pour assimiler l'ensemble des cours (ex: `3.5`).

### 7.2 Bloc « Contenu & Pédagogie »
- **Description courte** : Synthèse percutante de 1 à 2 phrases affichée sur les cartes du catalogue.
- **Description détaillée** : Présentation complète du programme, de la démarche pédagogique et des bénéfices concrets.
- **Objectifs pédagogiques** : Renseignez un objectif précis par ligne (le système convertit automatiquement chaque ligne en puce élégante sur la fiche publique) :
  ```text
  Identifier les propriétés vibratoires des 7 cristaux majeurs
  Maîtriser les protocoles de purification à l'eau et à la sauge
  Harmoniser ses centres énergétiques au quotidien
  ```
- **Prérequis** : Un prérequis par ligne (ex: *Aucune connaissance préalable requise*, *Disposer d'un jeu de quartz*).
- **Programme synthétique** : Vue d'ensemble du syllabus pour les apprenants pressés.

```
+-----------------------------------------------------------------------+
|  [CAPTURE D'ÉCRAN N°4 : BLOC PRÉSENTATION ET PÉDAGOGIE DE FORMATION]  |
|  Emplacement : /admin/courses/course/add/                             |
|  Éléments visibles : Champs Titre, Catégorie, Formateur, Niveau,      |
|  Objectifs pédagogiques et Prérequis.                                 |
+-----------------------------------------------------------------------+
```

---

## 8. AJOUT ET OPTIMISATION DE L'IMAGE DE COUVERTURE

L'image de couverture est la vitrine visuelle de votre formation sur le catalogue public et le tableau de bord apprenant.

### 8.1 Exigences techniques et formats acceptés
- **Formats autorisés :** JPEG, PNG, WebP.
- **Taille maximale brute :** 30 Mo (au-delà, le serveur refuse le fichier par sécurité).
- **Dimensions recommandées :** 1920 × 1080 pixels (ratio 16:9 haute définition).

### 8.2 Automatisation et optimisation intelligente
Vous n'avez pas besoin de compresser manuellement vos fichiers sur Photoshop :
- Le système LMS de Venus Luna intègre un moteur d'optimisation automatique (`apps/courses/image_utils.py`).
- Dès l'enregistrement, l'image est redimensionnée à un maximum de 1920px de large, orientée selon les métadonnées EXIF, convertie au format moderne ultra-léger **WebP** avec une qualité de 82%, et téléversée vers le cloud sécurisé **Cloudinary**.
- Le fichier résultant pèse moins de 500 Ko tout en conservant une netteté cristalline.

> **Erreur fréquente à éviter :**  
> Ne téléversez pas de fichiers PDF ou de vidéos dans ce champ. Seules les images sont acceptées. En cas de format invalide, un message d'erreur rouge vous indiquera immédiatement l'anomalie sans planter le formulaire.

---

## 9. CONFIGURATION DES TARIFS ET MODALITÉS D'ACCÈS

Dans le bloc **« Tarification & Modalités d'Accès »** :
- **Formation gratuite (Case à cocher)** :
  - Si cochée, le prix est automatiquement réinitialisé à 0 FCFA.
  - L'apprenant pourra s'inscrire en un seul clic sans passer par la passerelle de paiement.
- **Prix actuel (FCFA)** : Montant net en Francs CFA (XOF) pour l'acquisition de la formation (ex: `15000`).
- **Prix barré (FCFA)** : Champ optionnel pour afficher une promotion (ex: `25000`). Sur le catalogue, l'ancien prix apparaîtra barré à côté du prix remisé pour stimuler les conversions.

---

## 10. ORGANISATION ET STRUCTURATION DES MODULES

Une formation structurée se découpe en modules thématiques progressifs.

- **Objectif :** Créer l'ossature des modules au sein de la formation.
- **Chemin d'accès :** Directement en bas du formulaire de formation (Section **Modules de formation Inline**) OU via `Accueil Admin > Courses > Modules de formation`.

### Configuration d'un module :
1. **Titre du module** : Intitulé clair (ex: *Module 1 : Fondements et Découverte*).
2. **Ordre d'affichage** : Numéro séquentiel (0 pour le premier, 1 pour le second, etc.).
3. **Publié (Case à cocher)** : Permet de masquer temporairement un module en cours de préparation sans impacter les autres.
4. **Description** : Note d'introduction sur les notions abordées dans ce chapitre.

```
+-----------------------------------------------------------------------+
|  [CAPTURE D'ÉCRAN N°5 : GESTION DES MODULES INLINE DANS COURSE]       |
|  Emplacement : Section basse de /admin/courses/course/<id>/change/    |
|  Éléments visibles : Lignes de modules avec Titre, Ordre et coche     |
|  "Publié", bouton "Ajouter un autre Module de formation".             |
+-----------------------------------------------------------------------+
```

---

## 11. CRÉATION ET PARAMÉTRAGE DES LEÇONS

Chaque module contient une ou plusieurs leçons séquentielles.

- **Objectif :** Créer le contenu pédagogique individuel.
- **Chemin d'accès :** `Accueil Admin > Courses > Leçons > + Ajouter Leçon`.

### Champs de paramétrage d'une leçon :
1. **Module** : Sélectionnez le module auquel rattacher la leçon.
2. **Titre de la leçon** : Intitulé explicite (ex: *Leçon 1.1 : Histoire et Principes fondamentaux*).
3. **Type de leçon** :
   - `Vidéo` : Contenu principalement audiovisuel.
   - `Texte / Article` : Fiche synthétique, notes de cours ou guide de lecture.
   - `Document PDF` : Document d'étude à télécharger.
   - `Ressources téléchargeables` : Fichiers complémentaires (guides, planches d'exercices).
   - `Contenu mixte` : Combinaison de vidéo et de notes textuelles détaillées.
   - `Quiz d’évaluation` : Séance d'évaluation sommative.
4. **Durée estimée (minutes)** : Durée de visionnage ou de lecture (ex: `15`).
5. **Ordre d'affichage** : Position de la leçon dans le module (0, 1, 2...).
6. **Aperçu gratuit (`is_free_preview`)** :
   - Si cochée, cette leçon est ouverte à tous les visiteurs, y compris non inscrits.
   - C'est un puissant levier marketing pour donner un avant-goût de la qualité pédagogique de votre académie.
7. **Publiée** : Cochez pour rendre la leçon accessible aux apprenants.

---

## 12. AJOUT DE VIDÉOS ET RESSOURCES PÉDAGOGIQUES JOINTES

### 12.1 Intégration de vidéos
Dans le champ **Lien vidéo (video_url)**, vous pouvez renseigner :
- **YouTube** : Lien standard (`https://www.youtube.com/watch?v=...`) ou lien raccourci (`https://youtu.be/...`). Le lecteur Venus Luna le convertira automatiquement en lecteur sécurisé sans distractions.
- **Vimeo** : Lien de vidéo publique ou non listée (`https://vimeo.com/...`).
- **Fichier MP4 / Cloudinary direct** : URL directe se terminant par `.mp4`. Le lecteur utilisera la balise HTML5 native avec protection contre le clic droit de téléchargement (`controlsList="nodownload"`).

### 12.2 Ajout de pièces jointes et supports de cours
- **Document ou ressource jointe (`attachment_file`)** : Cliquez sur *Choisir un fichier* pour téléverser votre support (PDF, livret d'exercices, mémo imprimable).
- **Nom de la ressource (`attachment_name`)** : Donnez un nom convivial affiché à l'apprenant (ex: *Guide Pratique des 7 Chakras - PDF 12 pages*).

### 12.3 Contenu textuel et notes de cours
- **Courte description** : Résumé en quelques lignes.
- **Contenu textuel / Notes de cours (`content`)** : Zone de texte riche supportant des notes complètes, des exercices pratiques et des consignes de méditation.

---

## 13. CRÉATION DES QUIZ D'ÉVALUATION

Les quiz permettent de valider les acquis des apprenants à la fin d'un module ou en conclusion de formation.

- **Objectif :** Créer une évaluation notée.
- **Chemin d'accès :** `Accueil Admin > Courses > Quiz > + Ajouter Quiz`.

### Paramétrage du Quiz :
1. **Leçon associée** : Sélectionnez la leçon de type *Quiz d'évaluation* à laquelle rattacher ce quiz (relation 1 pour 1).
2. **Titre du quiz** : Intitulé (ex: *Évaluation des Connaissances - Module 1*).
3. **Instructions et consignes** : Conseils donnés à l'apprenant avant qu'il ne commence (ex: *Prenez le temps de bien lire chaque question. Ce quiz comporte 5 questions*).
4. **Score minimum requis (%)** : Pourcentage minimal pour réussir l'évaluation (la valeur par défaut recommandée est de **80%**).
5. **Nombre maximal de tentatives** :
   - Indiquez `0` pour autoriser un nombre illimité de tentatives (recommandé pour une approche bienveillante).
   - Indiquez un nombre (ex: `3`) si vous souhaitez restreindre les essais.

---

## 14. CONFIGURATION DES QUESTIONS, OPTIONS ET BARÈMES

Dans la page de modification du Quiz (ou via la table `Questions de quiz`) :

### 14.1 Ajout d'une question (`QuizQuestion`)
- **Énoncé de la question** : Texte clair de l'interrogation.
- **Type de question** :
  - *Choix unique* : Une seule réponse correcte (boutons radio).
  - *Choix multiples* : Plusieurs réponses correctes requises pour valider les points (cases à cocher).
- **Points** : Valeur de la question dans le barème (ex: `1` ou `2`).
- **Ordre d'affichage** : Ordre d'apparition dans le questionnaire.
- **Explication pédagogique** : Texte explicatif très utile affiché à l'apprenant **après** validation pour lui expliquer la bonne réponse et approfondir la notion.

### 14.2 Ajout des options de réponse (`QuizAnswerOption`)
Directement dans le tableau inline sous la question :
- Renseignez au moins 2 à 4 options.
- Saisissez le **Texte de l'option**.
- Cochez impérativement la case **Est une bonne réponse** pour l'option (ou les options) exacte(s).
- Spécifiez l'**Ordre**.

> **Règle absolue de sécurité :**  
> Les bonnes réponses ne sont JAMAIS envoyées dans le code source du navigateur de l'apprenant. La comparaison et la notation s'effectuent exclusivement sur le serveur Venus Luna lors de la soumission du formulaire POST.

```
+-----------------------------------------------------------------------+
|  [CAPTURE D'ÉCRAN N°6 : GESTION DES QUESTIONS ET OPTIONS DE QUIZ]     |
|  Emplacement : /admin/courses/quiz/<id>/change/                       |
|  Éléments visibles : Énoncé de question, type, barème, tableau inline |
|  des options avec la case verte "Est une bonne réponse".              |
+-----------------------------------------------------------------------+
```

---

## 15. GESTION ADMINISTRATIVE DES INSCRIPTIONS (ENROLLMENTS)

La table `Inscriptions` trace l'accès de chaque apprenant à chaque formation.

- **Chemin d'accès :** `Accueil Admin > Courses > Inscriptions`.

### 15.1 Colonnes du tableau de bord des inscriptions :
- **Apprenant** : Nom d'utilisateur et email.
- **Formation** : Titre du cours suivi.
- **Statut** : Badge coloré (*ACTIF* en vert, *TERMINÉ* en vert foncé, *EXPIRÉ* en rouge, *ANNULÉ* en gris).
- **Progression** : Jauge graphique dynamique indiquant le % exact d'avancement (ex: `65%`).
- **Source** : Provenance (*Gratuit*, *Achat CashPay*, *Attribution manuelle*).
- **Date d'inscription** et **Dernière activité**.

### 15.2 Inscrire manuellement un apprenant (Cadeau, Bourse, SAV) :
1. Cliquez sur **+ Ajouter Inscription**.
2. Sélectionnez l'**Apprenant** et la **Formation**.
3. Définissez le **Statut** sur `Actif`.
4. Définissez la **Source** sur `Attribution manuelle`.
5. Cliquez sur **Enregistrer**. L'apprenant verra instantanément la formation dans son espace personnel.

---

## 16. GESTION DES APPRENANTS ET PROFILS UTILISATEURS

Dans l'administration Django, les apprenants sont des comptes d'utilisateurs Django (`apps/accounts`).
- En consultant une inscription, l'administrateur peut visualiser la liste détaillée de toutes les leçons suivies via le sous-tableau **Progressions de leçons Inline** (date de complétion, dernière consultation).
- En cas de litige ou de demande d'assistance, vous pouvez vérifier exactement quelle leçon a été validée et à quel moment.

---

## 17. GESTION DES FORMATIONS GRATUITES

Pour lancer une formation gratuite de découverte (lead magnet ou cadeau de bienvenue) :
1. Sur la fiche de formation, cochez la case **Formation gratuite**.
2. Vérifiez que le prix est à `0`.
3. Assurez-vous que le statut est sur **Publiée**.
4. Sur le site public, le badge affichera fièrement **GRATUIT**, et les boutons dirigeront l'apprenant vers l'inscription immédiate en 1 clic sans passer par la commande.

---

## 18. GESTION DES FORMATIONS PAYANTES ET COMMANDES CASHPAY

Pour une formation payante :
1. Décochez **Formation gratuite** et saisissez le prix en Francs CFA (ex: `25000`).
2. Lorsqu'un client clique sur **Acheter avec CashPay** sur le site :
   - Une commande numérique sans frais de port (`Order`) est créée.
   - Le client est redirigé vers l'interface sécurisée CashPay pour payer par Mobile Money (T-Money ou Flooz).
   - Dès réception de la confirmation (Webhook ou retour paiement), le signal Django `post_save` passe automatiquement la commande en `paid` et crée l'`Enrollment` actif pour le compte de l'utilisateur.
3. **Cas de dépannage administratif :**  
   Si un client a effectué un virement manuel ou un paiement direct en agence, l'administrateur peut simplement créer manuellement l'inscription dans `Courses > Inscriptions` pour lui ouvrir l'accès immédiat.

---

## 19. SUIVI DE PROGRESSION DES APPRENANTS

Le système calcule l'avancement en temps réel :
$$\text{Progression (\%)} = \left(\frac{\text{Nombre de leçons validées}}{\text{Nombre total de leçons publiées}}\right) \times 100$$

- Chaque fois qu'un apprenant clique sur "Marquer comme terminée" ou réussit un quiz, la leçon passe à l'état `is_completed=True`.
- Dès que le compteur atteint 100%, le statut de l'inscription bascule automatiquement à **Terminé (`completed`)**, et la date de complétion est horodatée.

---

## 20. CONFIGURATION, DÉLIVRANCE ET VÉRIFICATION DES CERTIFICATS

### 20.1 Paramétrage sur la formation
Dans la fiche formation, bloc **« Certification »** :
- **Délivre un certificat de fin de formation** : Cochez cette case pour activer la certification.
- **Score minimum requis pour la certification (%)** : Seuil d'admissibilité (par défaut `80%`).

### 20.2 Génération automatique du certificat
Dès qu'un apprenant inscrit atteint 100% de progression sur une formation certifiante :
- Le système instancie un enregistrement dans la table `Certificate`.
- Un code unique inviolable est attribué (ex: `VL-4F9A2B81C3D5`).
- Le moteur vectoriel **ReportLab** dessine le document PDF aux dimensions A4 Paysage avec les polices, sceaux, bordures dorées et QR code de contrôle.
- Le certificat est instantanément disponible dans l'espace personnel de l'apprenant.

### 20.3 Révocation d'un certificat en cas d'anomalie
Dans `Accueil Admin > Courses > Certificats` :
- Ouvrez le certificat concerné.
- Décochez la case **Certificat valide**.
- Renseignez le **Motif de révocation** (ex: *Non-respect des conditions d'évaluation*).
- Désormais, toute personne scannant le QR code verra une notification d'avertissement rouge indiquant que le certificat a été révoqué.

```
+-----------------------------------------------------------------------+
|  [CAPTURE D'ÉCRAN N°7 : ADMINISTRATION D'UN CERTIFICAT OFFICIEL]      |
|  Emplacement : /admin/courses/certificate/<id>/change/                |
|  Éléments visibles : Code unique VL-..., Nom titulaire, Formation,    |
|  Date, coche "Certificat valide" et lien public de vérification.      |
+-----------------------------------------------------------------------+
```

---

## 21. PUBLICATION, MODIFICATION ET ARCHIVAGE DES COURS

### 21.1 Processus de relecture avant publication (Checklist Qualité)
Avant de faire passer une formation de *Brouillon* à *Publiée*, vérifiez :
- [ ] La couverture est nette et attrayante.
- [ ] La description comporte au moins 3 objectifs clairs et les prérequis.
- [ ] Tous les modules contiennent au moins une leçon.
- [ ] Les liens vidéos YouTube/Vimeo sont testés et fonctionnels.
- [ ] Au moins une leçon d'introduction est cochée en "Aperçu gratuit".
- [ ] Les éventuels quiz comportent leurs questions et leurs bonnes réponses cochées.
- [ ] La tarification en FCFA est exacte.

### 21.2 Actions de masse dans l'administration
Dans la liste des formations (`/admin/courses/course/`) :
- Cochez les cases en regard des cours visés.
- Dans le menu déroulant **Action**, choisissez :
  - *Publier les formations sélectionnées*
  - *Passer en brouillon les formations sélectionnées*
  - *Archiver les formations sélectionnées*
- Cliquez sur **Envoyer**.

---

## 22. BONNES PRATIQUES DE GESTION ET RECOMMANDATIONS ÉDITORIALES

1. **Rythme pédagogique :** Privilégiez des leçons courtes de 10 à 20 minutes plutôt qu'une unique vidéo de 2 heures. Cela améliore considérablement le taux de complétion.
2. **Qualité audio :** Une vidéo avec un son clair et limpide est bien plus appréciée qu'une vidéo en 4K avec un son parasité.
3. **Pédagogie positive dans les quiz :** Renseignez systématiquement le champ *Explication pédagogique* sur chaque question de quiz. L'apprenant apprend autant de ses erreurs que de ses réussites.
4. **Maintenance des liens externes :** Si vous hébergez vos vidéos sur YouTube, réglez la visibilité sur *Non répertoriée* (Unlisted) pour qu'elles ne soient pas accessibles publiquement en dehors de la plateforme Venus Luna.

---

## 23. EXERCICE PRATIQUE PAS-À-PAS : CRÉATION D'UNE FORMATION COMPLÈTE

Pour vous familiariser avec la plateforme, suivez cet exercice concret de bout en bout :

### Scénario : Création du cours « Initiation aux Rituels Sacrés de Protection »

#### Étape 1 : Créer la catégorie
- **Nom :** `Bien-être & Rituels Holistiques`
- **Icône :** `fa-feather-alt`
- **Ordre :** `4`

#### Étape 2 : Créer la formation
- **Titre :** `Initiation aux Rituels Sacrés de Protection et d'Harmonisation`
- **Catégorie :** `Bien-être & Rituels Holistiques`
- **Formateur :** Sélectionnez votre compte formateur.
- **Niveau :** `Débutant`
- **Durée estimée :** `2.5` heures.
- **Tarif :** Décocher "Formation gratuite", Prix actuel : `15000` FCFA, Prix barré : `25000` FCFA.
- **Description courte :** *Découvrez les protocoles ancestraux de fumigation, de purification des lieux et de protection énergétique.*
- **Objectifs pédagogiques :**
  ```text
  Comprendre les principes de la charge énergétique d'un lieu
  Maîtriser l'usage des herbes sacrées (sauge blanche, palo santo)
  Créer un rituel personnel d'ancrage et de protection
  ```
- **Prérequis :**
  ```text
  Aucun prérequis nécessaire
  Avoir une coupelle ou un récipient résistant à la chaleur
  ```
- **Statut :** `Brouillon` (pour le moment).
- Cliquez sur **Enregistrer et continuer les modifications**.

#### Étape 3 : Ajouter les modules et les leçons
**Module 1 : Les Fondements de la Purification Énergétique** (Ordre: 0)
- *Leçon 1.1 : Pourquoi et quand purifier son espace de vie ?*
  - Type : `Vidéo` | Durée : `12` min | Aperçu gratuit : `Coché` | Publiée : `Cochée`.
  - Lien vidéo : `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
- *Leçon 1.2 : Guide des herbes et résines traditionnelles*
  - Type : `Texte / Article` | Durée : `18` min | Aperçu gratuit : `Décoché` | Publiée : `Cochée`.
  - Contenu textuel : Rédiger les propriétés de la sauge, du cèdre et de la résine de benjoin.

**Module 2 : Protocoles Pratiques et Rituels** (Ordre: 1)
- *Leçon 2.1 : Déroulé pas-à-pas du rituel des quatre directions*
  - Type : `Mixte` | Durée : `20` min | Publiée : `Cochée`.
- *Leçon 2.2 : Évaluation finale de validation du cursus*
  - Type : `Quiz d’évaluation` | Durée : `10` min | Publiée : `Cochée`.

#### Étape 4 : Créer le Quiz de validation
- Rendez-vous dans `Courses > Quiz > + Ajouter Quiz`.
- Leçon associée : *Leçon 2.2 : Évaluation finale...*
- Titre : `Quiz de Certification - Rituels de Protection`
- Score minimum : `80%`
- Tentatives maximales : `0` (illimité).
- Ajoutez la Question 1 :
  - Énoncé : *Quelle plante est traditionnellement utilisée pour purifier un lieu des énergies stagnantes ?*
  - Type : *Choix unique* | Points : *1*.
  - Option 1 : *La sauge blanche* (Cocher : **Est une bonne réponse**).
  - Option 2 : *Le bambou décoratif*.
  - Option 3 : *L'orchidée*.
  - Explication : *La sauge blanche est reconnue depuis des millénaires pour sa haute fréquence purificatrice.*
- Enregistrez le quiz.

#### Étape 5 : Publication
- Retournez sur la fiche formation, basculez le statut sur **Publiée** et enregistrez.
- Rendez-vous sur `http://127.0.0.1:8000/formations/` pour admirer votre nouvelle formation en ligne !

---

## 24. FICHES MÉMO ET RÉSOLUTION DES ERREURS COURANTES

| Problème rencontré | Cause probable | Solution immédiate |
| :--- | :--- | :--- |
| **Erreur lors du téléversement de l'image de couverture** | Format de fichier non supporté (ex: SVG, TIFF, BMP) ou fichier endommagé. | Convertissez votre image en **JPG** ou **PNG** propre avant de la soumettre. |
| **La formation n'apparaît pas sur le catalogue** | Le statut est resté sur "Brouillon" ou la date de publication est future. | Passez le statut sur **Publiée** et vérifiez que la catégorie est bien active. |
| **L'apprenant ne voit pas les vidéos** | L'inscription est restée en statut "En attente" ou la vidéo est en mode "Privée" sur YouTube. | Vérifiez le statut de l'inscription dans `Courses > Inscriptions` et passez la vidéo en "Non répertoriée" sur YouTube. |
| **Le quiz ne valide pas la complétion de la leçon** | Le score obtenu par l'apprenant est inférieur au seuil requis (`passing_score`). | L'apprenant doit retenter le quiz et obtenir au moins le score requis (ex: 80%). |
| **Le certificat ne se télécharge pas** | Le nom de l'utilisateur comporte des caractères non reconnus ou la formation n'est pas terminée à 100%. | Vérifiez que toutes les leçons sont à l'état `Terminée` dans le profil de l'inscription. |

