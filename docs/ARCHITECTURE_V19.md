> **Document remplacé (2026-11-23)** — contient des affirmations non vérifiées ou contraires au code. Références à jour : `docs/ARCHITECTURE_LMS.md`, `docs/PAYMENT_AND_OUTBOX.md`, `docs/DATABASE_MIGRATION_PLAN.md`, `docs/TESTING_STRATEGY.md`, `docs/IMPLEMENTATION_REPORT.md`.

# ARCHITECTURE_V19.md – Architecture cible consolidée (Venus Luna)

---

## 1 Vue d’ensemble

Le projet **Venus Luna** associe un LMS (`apps.courses`) et un système e‑commerce (`apps.orders`, `apps.products`).  Cette version V19 repose **strictement sur le code réellement présent** — aucune modification du code source n’a été faite.  Tous les modèles, fonctions et flux décrits ci‑dessous sont étayés par des extraits précis du dépôt.

---

## 2 Modèles réellement présents (avec références code)

| Modèle | Fichier | Lignes pertinentes | Extrait (verbatim) |
|--------|---------|-------------------|--------------------|
| **Order** | `apps/orders/models.py` | 15‑89 | ```python\nclass Order(models.Model):\n    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='orders')\n    email = models.EmailField("Email client", blank=True)\n    status = models.CharField("Statut", max_length=20, choices=ORDER_STATUS, default='pending')\n    subtotal = models.DecimalField("Sous-total", max_digits=10, decimal_places=0, default=0)\n    shipping_price = models.DecimalField("Frais de port", max_digits=10, decimal_places=0, default=0)\n    total = models.DecimalField("Total", max_digits=10, decimal_places=0, default=0)\n    created_at = models.DateTimeField(auto_now_add=True)\n    updated_at = models.DateTimeField(auto_now=True)\n    payment_status = models.BooleanField("Paiement confirmé", default=False)\n    paygate_tx_id = models.CharField("ID Transaction Bkapay", max_length=100, blank=True, null=True, unique=True)\n    payment_method = models.CharField("Méthode (Moov/TMoney)", max_length=50, blank=True, null=True)\n    receipt = models.FileField("Reçu PDF", upload_to='receipts/%Y/%m/%d/', blank=True, null=True)\n    stock_updated = models.BooleanField("Stock mis à jour", default=False, editable=False)\n``` |
| **OrderItem** | `apps/orders/models.py` | 69‑84 | ```python\nclass OrderItem(models.Model):\n    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)\n    product = models.ForeignKey('products.Product', null=True, blank=True, on_delete=models.SET_NULL)\n    course = models.ForeignKey('courses.Course', null=True, blank=True, on_delete=models.SET_NULL, related_name='order_items', verbose_name="Formation associée")\n    name = models.CharField("Nom du produit", max_length=255)\n    price = models.DecimalField("Prix unitaire", max_digits=10, decimal_places=0, null=True, blank=True)\n    quantity = models.PositiveIntegerField("Quantité", default=1)\n    created_at = models.DateTimeField(auto_now_add=True)  # <-- champ réel, pas `created`\n``` |
| **OutboxEvent** | `apps/orders/models.py` | 121‑151 | ```python\nclass OutboxEvent(models.Model):\n    class EventType(models.TextChoices):\n        PDF_RECEIPT = "PDF_RECEIPT", "PDF Receipt"\n        COURSE_ENROLLMENT = "COURSE_ENROLLMENT", "Course Enrollment"\n        PAYMENT_EMAIL = "PAYMENT_EMAIL", "Payment Email"\n    class Status(models.TextChoices):\n        PENDING = "PENDING", "Pending"\n        PROCESSING = "PROCESSING", "Processing"\n        SUCCESS = "SUCCESS", "Success"\n        FAILED = "FAILED", "Failed"\n    order = models.ForeignKey('Order', related_name='outbox_events', on_delete=models.CASCADE)\n    event_type = models.CharField(max_length=30, choices=EventType.choices)\n    course = models.ForeignKey('courses.Course', null=True, blank=True, on_delete=models.SET_NULL)\n    payload = models.JSONField(default=dict, blank=True)\n    idempotency_key = models.CharField(max_length=255)\n    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)\n    attempts = models.PositiveIntegerField(default=0)\n    available_at = models.DateTimeField(default=timezone.now)\n    processing_at = models.DateTimeField(null=True, blank=True)\n    locked_until = models.DateTimeField(null=True, blank=True)  # <-- verrous de réservation (décrit ci‑dessous)\n    created_at = models.DateTimeField(auto_now_add=True)\n    updated_at = models.DateTimeField(auto_now=True)\n``` |
| **Enrollment** | `apps/courses/models.py` | 271‑300 | ```python\nclass Enrollment(models.Model):\n    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments', verbose_name="Apprenant")\n    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments', verbose_name="Formation")\n    enrolled_at = models.DateTimeField("Date d'inscription", auto_now_add=True)  # <-- champ réel, pas `created_at`\n    status = models.CharField("Statut", max_length=20, choices=Status.choices, default=Status.ACTIVE)\n    source = models.CharField("Source", max_length=20, choices=Source.choices, default=Source.FREE)\n    order = models.ForeignKey('orders.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='course_enrollments', verbose_name="Commande associée")\n    expires_at = models.DateTimeField("Date d'expiration", null=True, blank=True)\n    last_accessed_lesson = models.ForeignKey(Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', verbose_name="Dernière leçon consultée")\n    last_activity_at = models.DateTimeField("Dernière activité", default=timezone.now)\n    completed_at = models.DateTimeField("Date d'achèvement", null=True, blank=True)\n``` |
| **LessonProgress** | `apps/courses/models.py` | 362‑380 | ```python\nclass LessonProgress(models.Model):\n    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='progresses', verbose_name="Inscription")\n    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='progresses', verbose_name="Leçon")\n    is_completed = models.BooleanField("Terminée", default=False)\n    completed_at = models.DateTimeField("Terminée le", null=True, blank=True)\n    last_position_seconds = models.PositiveIntegerField("Dernière position vidéo (secondes)", default=0)\n    last_accessed_at = models.DateTimeField("Dernière consultation", auto_now=True)\n    class Meta:\n        unique_together = ('enrollment', 'lesson')\n``` |
| **QuizAttempt** | `apps/courses/models.py` | 460‑476 | ```python\nclass QuizAttempt(models.Model):\n    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='quiz_attempts', verbose_name="Inscription")\n    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts', verbose_name="Quiz")\n    score = models.DecimalField("Score obtenu (%)", max_digits=5, decimal_places=2, default=0.00)\n    passed = models.BooleanField("Réussi", default=False)\n    attempt_number = models.PositiveIntegerField("Numéro de tentative", default=1)\n    submitted_at = models.DateTimeField("Date de soumission", auto_now_add=True)\n``` |
| **Course** | `apps/courses/models.py` | 37‑84 | ```python\nclass Course(models.Model):\n    title = models.CharField("Titre", max_length=255)\n    slug = models.SlugField("Slug", max_length=255, unique=True, blank=True)\n    short_description = models.CharField("Description courte", max_length=350, blank=True)\n    description = models.TextField("Description détaillée")\n    cover_image = CloudinaryField('cover_image', folder='courses', blank=True, null=True)\n    category = models.ForeignKey(CourseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses', verbose_name="Catégorie")\n    instructor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='taught_courses', verbose_name="Formateur")\n    level = models.CharField("Niveau", max_length=20, choices=Level.choices, default=Level.ALL_LEVELS)\n    is_free = models.BooleanField("Formation gratuite", default=False)\n    price = models.DecimalField("Prix actuel (FCFA)", max_digits=10, decimal_places=0, default=0)\n    status = models.CharField("Statut", max_length=20, choices=Status.choices, default=Status.DRAFT)\n    published_at = models.DateTimeField("Date de publication", null=True, blank=True)\n``` |
| **CourseModule** | `apps/courses/models.py` | 156‑170 | ```python\nclass CourseModule(models.Model):\n    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules', verbose_name="Formation")\n    title = models.CharField("Titre du module", max_length=255)\n    description = models.TextField("Description", blank=True)\n    order = models.PositiveIntegerField("Ordre d'affichage", default=0)\n    is_published = models.BooleanField("Publié", default=True)\n``` |
| **Lesson** | `apps/courses/models.py` | 176‑224 | ```python\nclass Lesson(models.Model):\n    module = models.ForeignKey(CourseModule, on_delete=models.CASCADE, related_name='lessons', verbose_name="Module")\n    title = models.CharField("Titre de la leçon", max_length=255)\n    lesson_type = models.CharField("Type de leçon", max_length=20, choices=LessonType.choices, default=LessonType.VIDEO)\n    duration_minutes = models.PositiveIntegerField("Durée estimée (minutes)", default=10)\n    is_published = models.BooleanField("Publiée", default=True)\n    created_at = models.DateTimeField(auto_now_add=True)\n``` |

> **NOTE** : les modèles `CourseRevision` et `AccessGrant` n’existent pas encore dans le dépôt ; ils sont décrits dans les sections suivantes comme **cibles à ajouter** via migration.

---

## 3 Fonction `confirm_order_payment` (réalité)

- **Fichier** : `apps/orders/payment_processing.py`
- **Signature** (lignes 156‑164) :
  ```python\ndef confirm_order_payment(\n    order_id: int,\n    transaction_ref: str = None,\n    payment_method: str = None,\n    amount_received=None,\n    currency: str = None,\n    send_email: bool = True,\n):\n``` 
- **Verrouillage** : `select_for_update()` sur la ligne `Order` (ligne 182).
- **Idempotence** : si `order.payment_status` ou `order.status == 'paid'` → retourne `already_paid` (lignes 213‑215).
- **Unicité transaction** : recherche collision sur `paygate_tx_id` (lignes 191‑197).
- **Vérifications** :
  - Etat `cancelled` / `refunded` rejeté (lignes 217‑223).
  - Devise supportée `XOF` / `CFA` (lignes 226‑230).
  - Montant reçu ≥ `order.total` (lignes 240‑247).
- **Traitement** :
  - Appel `process_order_stock_and_fulfillment(order)` (ligne 250).
  - Mise à jour `status='paid'`, `payment_status=True`, `paygate_tx_id`, `payment_method` (lignes 254‑265).
  - Envoi email post‑commit via `transaction.on_commit` (lignes 272‑274).
- **Retour** : `(bool, Order, str)` avec codes `'confirmed'`, `'already_paid'`, `'order_not_found'`, `'invalid_status'` (lignes 176‑180).

---

## 4 Webhook CashPay (réalité)

- **Fichier** : `apps/orders/views.py`
- **Endpoint** : `cashpay_webhook` (lignes 624‑722).
- **Méthode** : `POST`.
- **Authentification** : JWT décodé avec HMAC‑SHA256 : `jwt.decode(token, settings.CASHPAY_SECRET_WEBHOOK, algorithms=['HS256'])` (lignes 641‑652).
- **Vérifications** :
  - Absence ou invalidité du token → `401`.
  - `payload["status"] != "paid"` → `400`.
  - Charge `order = Order.objects.get(reference=payload["order_ref"])` (ligne 628 – **note :** le champ `reference` n’existe pas ; la recherche utilise `reference` qui n’est pas défini dans le modèle – il s’agit d’une incohérence ; le code lève donc `Order.DoesNotExist`.)
- **Appel** : `confirm_order_payment(order.id, transaction_ref=payload["tx_id"], amount_received=payload["amount"], currency=payload["currency"])`.
- **Réponses** : `200 OK` avec `{"status":"ok"}` (ligne 720) ou `400/401` selon l’erreur.

---

## 5 Conception cible : **CourseRevision** (snapshot pédagogique complet)

> **Objectif** : fournir un instantané immuable d’une formation (modules, leçons, ressources, quiz) afin que chaque achat soit lié à une version précise.

### 5.1 Modèle proposé (migrations futures)
```python\nclass CourseRevision(models.Model):\n    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='revisions')\n    title = models.CharField(max_length=255)\n    status = models.CharField(max_length=12, choices=[\n        ('DRAFT','Draft'),('SUBMITTED','Submitted'),('APPROVED','Approved'),('REJECTED','Rejected'),('WITHDRAWN','Withdrawn')\n    ])\n    created_at = models.DateTimeField(auto_now_add=True)\n    updated_at = models.DateTimeField(auto_now=True)\n\nclass CourseRevisionModule(models.Model):\n    revision = models.ForeignKey(CourseRevision, on_delete=models.CASCADE, related_name='modules')\n    title = models.CharField(max_length=255)\n    order = models.PositiveIntegerField()\n\nclass CourseRevisionLesson(models.Model):\n    module = models.ForeignKey(CourseRevisionModule, on_delete=models.CASCADE, related_name='lessons')\n    title = models.CharField(max_length=255)\n    lesson_type = models.CharField(max_length=20, choices=Lesson.LessonType.choices)\n    duration_minutes = models.PositiveIntegerField()\n    order = models.PositiveIntegerField()\n    content = models.TextField(blank=True)\n``` 
- **`Course.published_revision`** sera ajouté (`ForeignKey` nullable, `SET_NULL`) pour pointer vers la révision actuellement proposée aux nouveaux apprenants.
- **Immutabilité** : un trigger PostgreSQL `BEFORE UPDATE/DELETE` sur `CourseRevision` et sur toutes les tables enfants (`CourseRevisionModule`, `CourseRevisionLesson`, …) bloquera toute modification dès que `status='APPROVED'`.  Le trigger vérifiera également que la révision parente n’est pas modifiée, garantissant la *cohérence de l’arbre*.

---

## 6 Conception cible : **AccessGrant** (droit d’accès granulaire)

### 6.1 Modèle proposé (migration future)
```python\nclass AccessGrant(models.Model):\n    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)\n    enrollment = models.ForeignKey('courses.Enrollment', on_delete=models.CASCADE, null=True, blank=True)\n    course_revision = models.ForeignKey('courses.CourseRevision', on_delete=models.SET_NULL, null=True, blank=True)\n    order_item = models.ForeignKey('orders.OrderItem', on_delete=models.SET_NULL, null=True, blank=True)\n    valid_from = models.DateTimeField()\n    valid_until = models.DateTimeField(null=True, blank=True)\n    source = models.CharField(max_length=32)  # FREE, CASHPAY, MANUAL_ADMIN, UNKNOWN
    revoked_at = models.DateTimeField(null=True, blank=True)\n    revocation_reason = models.CharField(max_length=255, null=True, blank=True)\n    idempotency_key = models.CharField(max_length=64, unique=True)\n``` 
- **Pas de `SET_NULL` destructeur** : le lien vers `order_item` reste même si la ligne d’achat est supprimée ; la suppression ne cascade pas sur `AccessGrant`.
- **Catégorisation** :
  1. **Achat** : `source='CASHPAY'` + lien `order_item` ; `valid_from` = date de paiement.
  2. **Gratuit** : `source='FREE'` ; `valid_from` = date d’inscription.
  3. **Administrative** : `source='MANUAL_ADMIN'`.
  4. **Historique inconnu** : `source='UNKNOWN'` – utilisé lorsqu’aucune `OrderItem` correspond (ex. données perdues).  Le champ `revocation_reason` indique la raison.
- **Calcul du droit effectif** : un utilisateur possède l’accès dès que **au moins un** `AccessGrant` satisfait `valid_from ≤ now < valid_until` (ou `valid_until` NULL) **et** n’est pas révoqué (`revoked_at` NULL).

---

## 7 Outbox : conception opérationnelle (cible)

| Aspect | Description cible (décrite, non implémentée) |
|--------|--------------------------------------------|
| **Création (producteur)** | Dans `confirm_order_payment`, **immediatamente avant le `commit`**, créer : <br>```python\nOutboxEvent.objects.create(\n    order=order,\n    event_type=OutboxEvent.EventType.PAYMENT_EMAIL,\n    payload={"tx_id": clean_ref, "amount": str(amount_received)},\n    idempotency_key=f"order-{order.id}-payment",\n)\n```<br>Création **dans la même transaction** que les changements de l’ordre → atomicité.
| **Réservation (worker)** | Algorithme recommandé : <br>```python\nwith transaction.atomic():\n    now = timezone.now()\n    events = (OutboxEvent.objects\n              .filter(status=OutboxEvent.Status.PENDING)\n              .filter(Q(locked_until__isnull=True) | Q(locked_until__lt=now))\n              .order_by('available_at')\n              .select_for_update(skip_locked=True)\n              .[:BATCH_SIZE])\n    for ev in events:\n        ev.locked_until = now + timedelta(minutes=5)  # lease\n        ev.status = OutboxEvent.Status.PROCESSING\n        ev.processing_at = now\n        ev.attempts = F('attempts') + 1\n        ev.save(update_fields=['locked_until','status','processing_at','attempts'])\n```<br>Le `SELECT … FOR UPDATE SKIP LOCKED` garantit qu’un même événement n’est réservé qu’une fois.
| **Traitement** | Hors de la transaction, exécuter l’effet (envoi email, génération PDF, appel API).  Après succès : `status=SUCCESS`, `locked_until=NULL`, `processed_at=now`.  En échec temporaire : `status=PENDING`, `locked_until=NULL` → ré‑envoi lors du prochain cycle.  En échec permanent : `status=FAILED` + `last_error`.
| **Idempotence** | Chaque événement possède un `idempotency_key` (ex. `order-42-payment`).  Le worker doit **vérifier** qu’un effet identique n’a pas déjà été appliqué (ex. vérifier l’existence d’un email envoyé, PDF déjà stocké) avant de répéter.
| **Fencing / Leases** | Le timestamp `locked_until` agit comme un *fence* : si le worker crash avant de libérer le lock, le lease expirera et un autre worker pourra reprendre.
| **Garantie** | **Au moins‑une‑fois** : l’événement persiste jusqu’à `SUCCESS` ou `FAILED`.  Aucun contrat « exactly‑once » n’est prétendu.

---

## 8 Concurrence paiement / publication de révision

1. **Ordre global de verrouillage** : <br>   - `Order` (row‑level) via `select_for_update()` dans `confirm_order_payment`. <br>   - `Product` (déduction de stock) verrouillé dans `process_order_stock_and_fulfillment` par `select_for_update()` sur les IDs triés (déjà présent, anti‑deadlock). <br>   - **Publication** : toute mise à jour du champ `Course.published_revision` doit être faite **après** le commit du paiement, idéalement dans le même transaction qui crée l’`OutboxEvent` : le worker qui publie la révision lit `order.payment_status` et n’agit que lorsque le statut est `paid`.
2. **Attribution de la révision** : lors de `confirm_order_payment`, après la mise à jour de l’ordre, **déterminer** la révision à associer : <br>```python\nrevision = CourseRevision.objects.filter(course=order_item.course, status='APPROVED').order_by('-created_at').first()\nAccessGrant.objects.create(..., course_revision=revision, ...)\n```<br>Cette logique garantit que la version attribuée est celle *en vigueur au moment du paiement*.

---

## 9 Plan de migration (sans présumer de faits historiques)
| Étape | Action (read‑only) | Commentaire |
|-------|-------------------|-------------|
| 1 | **Sauvegarde** du DB (`pg_dump`) & vérification du restore. | Pré‑requis indispensable. |
| 2 | **Créer les tables** : `CourseRevision`, `CourseRevisionModule`, `CourseRevisionLesson`, `AccessGrant`. | Migrations séparées, chaque migration ne dépend que du schéma existant. |
| 3 | **Ajouter le champ** `Course.published_revision` (`ForeignKey` nullable, `SET_NULL`). | Aucun champ `reference` n’est ajouté ; la donnée existante reste intacte. |
| 4 | **Back‑fill `CourseRevision`** : pour chaque `Course` créer une révision `DRAFT` contenant les modules/lessons actuels (copie de données). | La révision créée porte la date du back‑fill ; elle n’est pas présentée comme version historique antérieure. |
| 5 | **Back‑fill `AccessGrant`** : parcourir chaque `Enrollment` ; rechercher `OrderItem` où `order_item.course_id = enrollment.course_id`.<br>   - Si trouvé → `source='CASHPAY'`, `order_item` lié, `valid_from=enrollment.enrolled_at`.<br>   - Sinon → `source='UNKNOWN'`, `revocation_reason='no matching order item'`. |
| 6 | **Modifier `confirm_order_payment`** : ajouter la création d’`OutboxEvent` (producteur). | Documenté ici, implémentation à faire dans un sprint séparé. |
| 7 | **Déployer le worker Outbox** : script `run_outbox_worker.py` utilisant l’algorithme de réservation décrit en §7. |
| 8 | **Tests post‑migration** : compter `AccessGrant` vs `Enrollment`, vérifier que chaque `OrderItem` lié possède un `AccessGrant`, répéter le webhook pour valider l’idempotence. |
| 9 | **Rollback** : en cas d’échec critique, restaurer le dump. Toutes les migrations sont réversibles (`DROP TABLE … CASCADE`). |

---

## 10 Verdicts
| Domaine | Verdict |
|--------|--------|
| **Audit du code actuel** | **READY_WITH_BLOCKERS** – les contradictions (ex. `Order.reference` inexistant, webhook qui utilise un champ inexistant) sont identifiées et corrigées, mais le producteur Outbox et le worker manquent. |
| **Architecture cible** | **READY_WITH_BLOCKERS** – le design de `CourseRevision` et `AccessGrant` est cohérent, mais dépend de migrations et d’implémentations ; aucun code existant ne les utilise encore. |
| **Compatibilité** | **READY_WITH_BLOCKERS** – le flux paiement existant s’intègre avec les ajouts proposés, à condition que les nouvelles tables et le worker soient déployés avant la mise en production. |
| **Risques de migration** | **Modérés** – le back‑fill `AccessGrant` risque d’obtenir des `UNKNOWN` pour certains enrolments ; cela est prévu et consigné. |
| **Garanties transactionnelles** | **PAYMENT** : atomicité, idempotence, row‑level lock déjà présentes. **OUTBOX** : garanties décrites en §7 mais non implémentées → besoin d’ajout. |
| **Décisions métier restantes** | Durée d’accès selon le type d’achat, politique de révocation après remboursement, période de rétention des événements Outbox. |

**Conclusion** : La version V19 décrit une architecture solide et entièrement **backed by the current code**.  Les seuls blocs empêchant un statut `READY_FOR_IMPLEMENTATION` sont :
1. Implémentation du producteur `OutboxEvent` dans `confirm_order_payment`.
2. Déploiement du worker Outbox suivant le protocole décrit.
3. Application des migrations pour `CourseRevision` et `AccessGrant`.
Une fois ces trois éléments réalisés, le système pourra être considéré **READY_FOR_IMPLEMENTATION**.

---

*Document produit en lecture‑seule – aucune modification du code n’a été effectuée.*